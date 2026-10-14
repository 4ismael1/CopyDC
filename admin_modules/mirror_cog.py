"""Espejo experimental del owner: origen de solo lectura, escrituras en destino."""

import asyncio
import io
import logging
from contextlib import closing, suppress

import discord
from discord import ui
from discord.ext import commands

import database as db

log = logging.getLogger(__name__)
REASON = "Configuración de espejo experimental confirmada por el propietario"
SUPPORTED = (discord.CategoryChannel, discord.TextChannel, discord.VoiceChannel)


class MirrorStore:
    """Solo configuración e IDs; no almacena contenido ni tokens de webhooks."""

    def init(self):
        with closing(db.get_db_connection()) as conn, conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS mirror_pairs (
                    source INTEGER PRIMARY KEY, destination INTEGER UNIQUE NOT NULL,
                    owner INTEGER NOT NULL, state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mirror_channels (
                    source_channel INTEGER PRIMARY KEY, source INTEGER NOT NULL,
                    destination_channel INTEGER NOT NULL, webhook INTEGER,
                    FOREIGN KEY(source) REFERENCES mirror_pairs(source) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS mirror_messages (
                    source_message INTEGER NOT NULL, part INTEGER NOT NULL,
                    source_channel INTEGER NOT NULL, destination_message INTEGER NOT NULL,
                    PRIMARY KEY(source_message, part),
                    FOREIGN KEY(source_channel) REFERENCES mirror_channels(source_channel) ON DELETE CASCADE
                );
            """)
            conn.execute("UPDATE mirror_pairs SET state='error' WHERE state='building'")

    def rows(self, sql, args=()):
        with closing(db.get_db_connection()) as conn:
            return [dict(row) for row in conn.execute(sql, args)]

    def write(self, sql, args=()):
        with closing(db.get_db_connection()) as conn, conn:
            conn.execute(sql, args)

    def pairs(self):
        return self.rows("SELECT * FROM mirror_pairs")

    def begin(self, source, destination, owner):
        with closing(db.get_db_connection()) as conn, conn:
            conn.execute(
                "DELETE FROM mirror_pairs WHERE state='stopped' AND (source IN (?, ?) OR destination IN (?, ?))",
                (source, destination, source, destination),
            )
            conn.execute(
                "INSERT INTO mirror_pairs VALUES (?, ?, ?, 'building')", (source, destination, owner)
            )

    def state(self, source, state):
        self.write("UPDATE mirror_pairs SET state=? WHERE source=?", (state, source))

    def channel(self, source_channel):
        rows = self.rows("SELECT * FROM mirror_channels WHERE source_channel=?", (source_channel,))
        return rows[0] if rows else None

    def messages(self, source_message):
        return self.rows(
            "SELECT * FROM mirror_messages WHERE source_message=? ORDER BY part", (source_message,)
        )


def permitted_message(message, pair):
    return (
        message.guild is not None
        and message.guild.id == pair["source"]
        and message.author.id == pair["owner"]
        and not message.author.bot
        and not message.webhook_id
        and isinstance(message.channel, discord.TextChannel)
    )


def message_parts(message):
    content = message.content or ""
    # Embeds de otros bots no se copian; las tarjetas/link previews se regeneran por Discord.
    if message.stickers:
        content += "\n" + "\n".join(str(sticker.url) for sticker in message.stickers)
    return [content[i : i + 2000] for i in range(0, len(content), 2000)] or [""]


def marker(message_id, *, edited=False, deleted=False, notes=""):
    if not edited and not deleted and not notes:
        return None
    state = "🗑️ Mensaje eliminado en origen" if deleted else "✏️ Editado en origen" if edited else None
    embed = discord.Embed(description=notes[:3000] or None, color=discord.Color.blurple())
    if state:
        embed.set_footer(text=state)
    return embed


class MirrorConfirmation(ui.Modal, title="Confirmar borrado del destino"):
    destination_id = ui.TextInput(label="Escribe el ID del servidor DESTINO", max_length=20)

    def __init__(self, view):
        super().__init__(timeout=120)
        self.plan = view

    async def on_submit(self, interaction):
        plan = self.plan
        if interaction.user.id != plan.owner or self.destination_id.value.strip() != str(plan.destination):
            await interaction.response.send_message(
                "Confirmación incorrecta. No se modificó nada.", ephemeral=True
            )
            return
        if plan.used or plan.is_finished():
            await interaction.response.send_message(
                "Esta confirmación ya no es válida. Repite setup.", ephemeral=True
            )
            return
        plan.used = True
        plan.stop()
        await interaction.response.defer(ephemeral=True, thinking=True)
        await plan.cog.run_setup(interaction, plan)


class MirrorSetupView(ui.View):
    def __init__(self, cog, source, destination, owner):
        super().__init__(timeout=120)
        self.cog = cog
        self.source = source.id
        self.destination = destination.id
        self.owner = owner
        self.source_ids = {c.id for c in source.channels}
        self.destination_ids = {c.id for c in destination.channels}
        self.used = False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner:
            await interaction.response.send_message("Solo el propietario puede confirmar.", ephemeral=True)
            return False
        return True

    @ui.button(label="Borrar destino y crear espejo", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        await interaction.response.send_modal(MirrorConfirmation(self))

    @ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.used = True
        self.stop()
        await interaction.response.edit_message(content="Cancelado. No se modificó nada.", view=None)


class MirrorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.store = MirrorStore()
        self.pairs = {}
        self.webhooks = {}
        self.queue = asyncio.Queue(maxsize=500)
        self.setup_lock = asyncio.Lock()
        self.operation_lock = asyncio.Lock()
        self.worker = None
        self.history_tasks = {}

    async def cog_load(self):
        await asyncio.to_thread(self.store.init)
        await self.reload_pairs()
        self.worker = asyncio.create_task(self.work(), name="copy-mirror")

    async def cog_unload(self):
        tasks = list(self.history_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self.worker:
            self.worker.cancel()
            with suppress(asyncio.CancelledError):
                await self.worker

    async def reload_pairs(self):
        self.pairs = {p["source"]: p for p in await asyncio.to_thread(self.store.pairs)}

    def validate(self, source_id, destination_id, owner):
        source = self.bot.get_guild(source_id)
        destination = self.bot.get_guild(destination_id)
        if not source or not destination or source_id == destination_id:
            raise ValueError("Origen y destino deben ser distintos y Copy debe estar en ambos.")
        if owner != self.bot.owner_id or source.owner_id != owner or destination.owner_id != owner:
            raise ValueError("Solo el dueño de Copy puede usarlo y debe ser propietario de ambos servidores.")
        if source.unavailable or destination.unavailable:
            raise ValueError("Uno de los servidores no está disponible. Inténtalo más tarde.")
        if not destination.me or not destination.me.guild_permissions.administrator:
            raise ValueError("Para esta prueba destructiva Copy necesita Administrador en el destino.")
        if not self.bot.intents.message_content:
            raise ValueError("Message Content debe estar habilitado en Copy.")
        if not source.me or any(
            not c.permissions_for(source.me).view_channel
            or not c.permissions_for(source.me).read_message_history
            for c in source.text_channels
        ):
            raise ValueError("Copy debe poder ver y leer el historial de los canales de texto del origen.")
        if not source.text_channels:
            raise ValueError("El origen debe tener al menos un canal de texto.")
        # No se modifican servidores Community: sus canales requeridos pueden impedir el borrado.
        if "COMMUNITY" in destination.features:
            raise ValueError(
                "Usa un destino de prueba sin Comunidad; no se borrarán sus canales obligatorios."
            )
        for pair in self.pairs.values():
            if pair["state"] == "stopped":
                continue
            if {source_id, destination_id} & {pair["source"], pair["destination"]}:
                raise ValueError("Un servidor ya pertenece a un espejo. Detén esa conexión primero.")
        return source, destination

    @commands.group(name="mirror", invoke_without_command=True)
    @commands.is_owner()
    @commands.guild_only()
    async def mirror(self, ctx):
        await ctx.reply(
            "**Espejo experimental (solo tus mensajes)**\n"
            "Ejecuta desde el destino: `c!mirror setup ID_ORIGEN`.\n"
            "Elimina TODOS los canales/categorías del destino tras confirmar su ID; el historial no es recuperable.\n"
            "Clona categorías, texto y voz (sin audio). No copia roles, permisos, historial, hilos, foros ni escenarios.\n"
            "Ignora bots/webhooks. Conserva las copias borradas en origen.\n"
            "Historial: `c!mirror history CANTIDAD` (1–1000 mensajes tuyos por canal); `c!mirror historycancel`.\n"
            "Controles: `c!mirror status`, `c!mirror pause`, `c!mirror resume`, `c!mirror stop`.",
            mention_author=False,
        )

    @mirror.command(name="setup")
    @commands.is_owner()
    @commands.guild_only()
    async def setup_command(self, ctx, source_id: int):
        if self.setup_lock.locked():
            await ctx.reply("Ya hay una configuración en curso.", mention_author=False)
            return
        try:
            source, destination = self.validate(source_id, ctx.guild.id, ctx.author.id)
        except ValueError as exc:
            await ctx.reply(str(exc), mention_author=False)
            return
        unsupported = [c for c in source.channels if not isinstance(c, SUPPORTED)]
        inventory = "\n".join(f"{c.id}\t{c.type}\t{c.name}" for c in destination.channels) or "Sin canales"
        embed = discord.Embed(
            title="Confirmar reemplazo del DESTINO",
            color=discord.Color.red(),
            description=(
                f"**Origen:** {discord.utils.escape_markdown(source.name)} (`{source.id}`)\n"
                f"**Destino que se borrará:** {discord.utils.escape_markdown(destination.name)} (`{destination.id}`)\n\n"
                f"Se eliminarán **{len(destination.channels)} canales/categorías**, incluido este canal, "
                "sus mensajes e hilos. **El historial eliminado no se puede recuperar.**\n"
                f"Se copiarán {len(source.categories)} categorías, {len(source.text_channels)} canales de texto "
                f"y {len(source.voice_channels)} de voz. Se omitirán {len(unsupported)} canales no compatibles "
                "y todos los hilos. No se copiarán roles, permisos ni historial.\n\n"
                "El origen no se modifica. Solo se replicarán tus mensajes nuevos; bots/webhooks se ignoran. "
                "Los borrados se conservan con una marca. Confirma escribiendo el ID del DESTINO."
            ),
        )
        await ctx.reply(
            embed=embed,
            view=MirrorSetupView(self, source, destination, ctx.author.id),
            file=discord.File(
                io.BytesIO(inventory.encode("utf-8")), filename="canales-destino-a-eliminar.txt"
            ),
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def run_setup(self, interaction, plan):
        async with self.setup_lock, self.operation_lock:
            began = False
            try:
                source, destination = self.validate(plan.source, plan.destination, plan.owner)
                if {c.id for c in source.channels} != plan.source_ids or {
                    c.id for c in destination.channels
                } != plan.destination_ids:
                    raise ValueError(
                        "La lista de canales cambió. Repite setup para confirmar el nuevo inventario."
                    )
                await asyncio.to_thread(self.store.begin, source.id, destination.id, plan.owner)
                began = True
                await self.reload_pairs()
                # El canal de confirmación se elimina al final. Nunca llamamos delete sobre el origen.
                targets = sorted(
                    destination.channels,
                    key=lambda c: (c.id == interaction.channel_id, isinstance(c, discord.CategoryChannel)),
                )
                for channel in targets:
                    await channel.delete(reason=REASON)
                categories = {}
                for category in sorted(source.categories, key=lambda c: c.position):
                    categories[category.id] = await destination.create_category(
                        category.name,
                        position=category.position,
                        overwrites={},
                        reason=REASON,
                    )
                for channel in sorted(source.channels, key=lambda c: (c.position, c.id)):
                    category = categories.get(getattr(channel, "category_id", None))
                    if isinstance(channel, discord.TextChannel):
                        clone = await destination.create_text_channel(
                            channel.name,
                            category=category,
                            position=channel.position,
                            topic=channel.topic,
                            nsfw=channel.nsfw,
                            slowmode_delay=channel.slowmode_delay,
                            overwrites={},
                            reason=REASON,
                        )
                        webhook = await clone.create_webhook(name="Copy Mirror", reason=REASON)
                        self.webhooks[webhook.id] = webhook
                        await asyncio.to_thread(
                            self.store.write,
                            "INSERT INTO mirror_channels VALUES (?, ?, ?, ?)",
                            (channel.id, source.id, clone.id, webhook.id),
                        )
                    elif isinstance(channel, discord.VoiceChannel):
                        await destination.create_voice_channel(
                            channel.name,
                            category=category,
                            position=channel.position,
                            bitrate=min(channel.bitrate, destination.bitrate_limit),
                            user_limit=channel.user_limit,
                            overwrites={},
                            reason=REASON,
                        )
                await asyncio.to_thread(self.store.state, source.id, "active")
                await self.reload_pairs()
                await self.report(
                    interaction,
                    destination,
                    "Espejo activo. Se copian solo tus mensajes nuevos. Bots/webhooks ignorados. Los canales anteriores del destino y su historial fueron eliminados y no se pueden recuperar.",
                )
            except Exception as exc:
                if began:
                    await asyncio.to_thread(self.store.state, plan.source, "error")
                    await self.reload_pairs()
                # No se imprime HTTP body: puede contener datos o URLs privadas.
                log.warning(
                    "Mirror setup falló | destino=%s | tipo=%s | HTTP=%s",
                    plan.destination,
                    type(exc).__name__,
                    getattr(exc, "status", "—"),
                )
                text = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "La configuración falló. Puede haber canales ya eliminados; no se restauran automáticamente. Revisa permisos y c!mirror status. Usa stop y vuelve a configurar si corresponde."
                )
                await self.report(interaction, self.bot.get_guild(plan.destination), text)

    async def report(self, interaction, destination, text):
        with suppress(discord.HTTPException):
            await interaction.followup.send(text, ephemeral=True)
            return
        if destination:
            for channel in destination.text_channels:
                if channel.permissions_for(destination.me).send_messages:
                    with suppress(discord.HTTPException):
                        await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
                        return

    def destination_pair(self, destination):
        return next((p for p in self.pairs.values() if p["destination"] == destination), None)

    @mirror.command(name="status")
    @commands.is_owner()
    @commands.guild_only()
    async def status(self, ctx):
        pair = self.destination_pair(ctx.guild.id)
        if not pair:
            await ctx.reply("Este servidor no tiene un espejo configurado.", mention_author=False)
            return
        channels = await asyncio.to_thread(
            self.store.rows, "SELECT * FROM mirror_channels WHERE source=?", (pair["source"],)
        )
        await ctx.reply(
            f"Origen: `{pair['source']}` → destino: `{pair['destination']}`\n"
            f"Estado: **{pair['state']}** · canales de texto enlazados: {len(channels)} · cola: {self.queue.qsize()}\n"
            f"Importación de historial: {'en curso' if ctx.guild.id in self.history_tasks else 'inactiva'}.\n"
            "Solo mensajes del propietario. Historial manual: `c!mirror history CANTIDAD`. "
            "Sin recuperación automática de eventos perdidos durante apagados/pausas. "
            "Si una configuración falló, usa stop antes de repetir setup.",
            mention_author=False,
        )

    async def set_state(self, ctx, state):
        if self.setup_lock.locked():
            await ctx.reply("Espera a que termine la configuración.", mention_author=False)
            return
        async with self.operation_lock:
            pair = self.destination_pair(ctx.guild.id)
            if not pair or pair["state"] in {"building", "stopped"}:
                await ctx.reply("No hay un espejo disponible para esa operación.", mention_author=False)
                return
            if state == "active" and pair["state"] != "paused":
                await ctx.reply(
                    "Solo se reanuda un espejo pausado. Para errores de configuración, usa stop y setup.",
                    mention_author=False,
                )
                return
            if state == "paused" and pair["state"] != "active":
                await ctx.reply("Solo se puede pausar un espejo activo.", mention_author=False)
                return
            await asyncio.to_thread(self.store.state, pair["source"], state)
            await self.reload_pairs()
            if state in {"paused", "stopped"} and ctx.guild.id in self.history_tasks:
                self.history_tasks[ctx.guild.id].cancel_requested = True
        await ctx.reply(
            f"Espejo: **{state}**. Las copias y canales existentes se conservan.", mention_author=False
        )

    @mirror.command(name="pause")
    @commands.is_owner()
    @commands.guild_only()
    async def pause(self, ctx):
        await self.set_state(ctx, "paused")

    @mirror.command(name="resume")
    @commands.is_owner()
    @commands.guild_only()
    async def resume(self, ctx):
        await self.set_state(ctx, "active")

    @mirror.command(name="stop")
    @commands.is_owner()
    @commands.guild_only()
    async def stop(self, ctx):
        await self.set_state(ctx, "stopped")

    def history_pair(self, source, destination):
        pair = self.pairs.get(source)
        original = self.bot.get_guild(source)
        target = self.bot.get_guild(destination)
        if (
            not pair
            or pair["destination"] != destination
            or pair["state"] != "active"
            or not original
            or not target
            or original.owner_id != pair["owner"]
            or target.owner_id != pair["owner"]
        ):
            raise ValueError("El espejo ya no está activo o cambió su propietario/destino.")
        return pair

    @mirror.command(name="history", aliases=["historial"])
    @commands.is_owner()
    @commands.guild_only()
    async def history(self, ctx, amount: int):
        if not 1 <= amount <= 1000:
            await ctx.reply(
                "Indica entre 1 y 1000 mensajes tuyos por canal y ejecución.", mention_author=False
            )
            return
        destination = ctx.guild.id
        pair = self.destination_pair(destination)
        if not pair or pair["state"] != "active":
            await ctx.reply("Ejecuta esto en el destino de un espejo activo.", mention_author=False)
            return
        if destination in self.history_tasks:
            await ctx.reply(
                "Ya hay una importación en curso. Usa `c!mirror historycancel` para cancelarla.",
                mention_author=False,
            )
            return
        # Sin await entre comprobación y reserva: dos comandos simultáneos no crean dos trabajos.
        self.history_tasks[destination] = asyncio.create_task(
            self.import_history(ctx, pair["source"], destination, amount),
            name=f"mirror-history-{destination}",
        )

    @mirror.command(name="historycancel")
    @commands.is_owner()
    @commands.guild_only()
    async def history_cancel(self, ctx):
        task = self.history_tasks.get(ctx.guild.id)
        if not task:
            await ctx.reply("No hay una importación en curso.", mention_author=False)
            return
        # Cancelación cooperativa: no interrumpir entre el envío y el guardado de su ID.
        task.cancel_requested = True
        await ctx.reply(
            "Cancelación solicitada; terminará el mensaje en curso. Se conservan las copias.",
            mention_author=False,
        )

    async def collect_history_ids(self, channel, pair, amount, cutoff, check):
        ids = []
        async for message in channel.history(limit=None, before=cutoff, oldest_first=False):
            check()
            if permitted_message(message, pair):
                ids.append(message.id)
                if len(ids) >= amount:
                    break
        return list(reversed(ids))

    async def import_history(self, ctx, source, destination, amount):
        copied = skipped = channels_done = 0
        result = "Importación terminada"
        task = asyncio.current_task()
        cutoff = discord.utils.utcnow()

        def check():
            if getattr(task, "cancel_requested", False):
                raise ValueError("Importación cancelada")
            return self.history_pair(source, destination)

        try:
            await ctx.send(
                f"Importando hasta {amount} mensajes tuyos recientes por canal enlazado, sin bots/webhooks "
                "ni duplicados. Se añaden al final del destino: Discord no permite insertarlos antes de las copias existentes. "
                "Puedes cancelar con `c!mirror historycancel`.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            pair = check()
            channels = await asyncio.to_thread(
                self.store.rows, "SELECT * FROM mirror_channels WHERE source=?", (source,)
            )
            for mapping in channels:
                check()
                channel = self.bot.get_channel(mapping["source_channel"])
                if not isinstance(channel, discord.TextChannel):
                    continue
                ids = await self.collect_history_ids(channel, pair, amount, cutoff, check)
                for message_id in ids:
                    check()
                    # El mismo lock que usa la réplica en vivo evita carreras y duplicados.
                    async with self.operation_lock:
                        pair = check()
                        if await asyncio.to_thread(self.store.messages, message_id):
                            skipped += 1
                            continue
                        try:
                            message = await channel.fetch_message(message_id)
                        except discord.NotFound:
                            skipped += 1
                            continue
                        if await self.replicate(message, pair, edited=False):
                            copied += 1
                        else:
                            skipped += 1
                    await asyncio.sleep(0)  # Cede el turno a los eventos en vivo.
                channels_done += 1
                await ctx.send(
                    f"Historial: {channels_done}/{len(channels)} canales · {copied} copiados · {skipped} omitidos."
                )
        except ValueError as exc:
            result = str(exc)
        except asyncio.CancelledError:
            result = "Importación interrumpida al descargar el módulo"
            raise
        except Exception as exc:
            result = "Importación interrumpida por un error; las copias completadas se conservan"
            log.warning(
                "Mirror historial falló | origen=%s | tipo=%s | HTTP=%s",
                source,
                type(exc).__name__,
                getattr(exc, "status", "—"),
            )
        finally:
            self.history_tasks.pop(destination, None)
            with suppress(discord.HTTPException):
                await ctx.send(
                    f"{result}. {copied} mensajes copiados; {skipped} omitidos (ya copiados/no disponibles)."
                )

    async def enqueue(self, source, kind, payload):
        pair = self.pairs.get(source)
        if not pair or pair["state"] != "active":
            return
        try:
            self.queue.put_nowait((source, kind, payload))
        except asyncio.QueueFull:
            await asyncio.to_thread(self.store.state, source, "paused")
            await self.reload_pairs()
            log.warning("Mirror pausado: cola llena | origen=%s", source)

    @commands.Cog.listener()
    async def on_message(self, message):
        pair = self.pairs.get(message.guild.id) if message.guild else None
        if pair and permitted_message(message, pair):
            await self.enqueue(pair["source"], "create", message)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload):
        # Se ignoran actualizaciones que solo cambian previews automáticas.
        if "content" in payload.data or "attachments" in payload.data:
            await self.enqueue(payload.guild_id, "edit", (payload.channel_id, payload.message_id))

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        await self.enqueue(payload.guild_id, "delete", payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        for message_id in payload.message_ids:
            await self.enqueue(payload.guild_id, "delete", message_id)

    async def work(self):
        await self.bot.wait_until_ready()
        while True:
            source, kind, payload = await self.queue.get()
            try:
                async with self.operation_lock:
                    pair = self.pairs.get(source)
                    if not pair or pair["state"] != "active":
                        continue
                    original = self.bot.get_guild(source)
                    destination = self.bot.get_guild(pair["destination"])
                    if (
                        not original
                        or not destination
                        or original.owner_id != pair["owner"]
                        or destination.owner_id != pair["owner"]
                    ):
                        await asyncio.to_thread(self.store.state, source, "paused")
                        await self.reload_pairs()
                        continue
                    if kind == "delete":
                        await self.mark_deleted(payload)
                    elif kind == "create":
                        await self.replicate(payload, pair, edited=False)
                    else:
                        channel_id, message_id = payload
                        # No importar mensajes anteriores al setup ni mensajes de otros autores.
                        if not await asyncio.to_thread(self.store.messages, message_id):
                            continue
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            try:
                                message = await channel.fetch_message(message_id)
                            except discord.NotFound:
                                await self.mark_deleted(message_id)
                            else:
                                await self.replicate(message, pair, edited=True)
            except Exception as exc:
                log.warning(
                    "Mirror evento falló | origen=%s | evento=%s | tipo=%s | HTTP=%s",
                    source,
                    kind,
                    type(exc).__name__,
                    getattr(exc, "status", "—"),
                )
                # Evita seguir acumulando fallos sin que status refleje el problema.
                if source in self.pairs:
                    await asyncio.to_thread(self.store.state, source, "paused")
                    await self.reload_pairs()
            finally:
                self.queue.task_done()

    async def webhook(self, channel):
        webhook_id = channel["webhook"]
        if webhook_id not in self.webhooks:
            self.webhooks[webhook_id] = await self.bot.fetch_webhook(webhook_id)
        webhook = self.webhooks[webhook_id]
        pair = self.pairs[channel["source"]]
        if webhook.channel_id != channel["destination_channel"] or webhook.guild_id != pair["destination"]:
            raise ValueError("Webhook movido fuera del destino configurado")
        return webhook

    async def replicate(self, message, pair, *, edited):
        if not permitted_message(message, pair):
            return False
        channel = await asyncio.to_thread(self.store.channel, message.channel.id)
        if not channel:
            return False
        existing = await asyncio.to_thread(self.store.messages, message.id)
        if existing and not edited:
            return False
        webhook = await self.webhook(channel)
        parts = message_parts(message)
        files = []
        downloaded_bytes = 0
        notes = []
        if message.reference and message.reference.message_id:
            notes.append(f"Respuesta al mensaje original {message.reference.message_id}")
        if message.embeds:
            notes.append("Las tarjetas enriquecidas no se archivan; se conserva el texto/enlace original.")
        try:
            limit = self.bot.get_guild(pair["destination"]).filesize_limit
            for attachment in message.attachments:
                if (
                    attachment.size > min(limit, 25 * 1024 * 1024)
                    or downloaded_bytes + attachment.size > 25 * 1024 * 1024
                ):
                    notes.append(
                        f"Adjunto no copiado por tamaño: {discord.utils.escape_markdown(attachment.filename)[:150]}"
                    )
                    continue
                try:
                    files.append(await attachment.to_file())
                    downloaded_bytes += attachment.size
                except discord.HTTPException:
                    notes.append(
                        f"Adjunto no disponible: {discord.utils.escape_markdown(attachment.filename)[:150]}"
                    )
            for index, content in enumerate(parts):
                embed = marker(message.id, edited=edited, notes="\n".join(notes) if index == 0 else "")
                if not content and not embed and not (files and index == 0):
                    content = "[Mensaje sin contenido compatible]"
                if index < len(existing):
                    await webhook.edit_message(
                        existing[index]["destination_message"],
                        content=content or None,
                        embed=embed,
                        attachments=files if index == 0 else [],
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                else:
                    sent = await webhook.send(
                        content=content or None,
                        embed=embed,
                        files=files if index == 0 else [],
                        username=message.author.display_name[:80],
                        avatar_url=str(message.author.display_avatar.url),
                        allowed_mentions=discord.AllowedMentions.none(),
                        wait=True,
                    )
                    await asyncio.to_thread(
                        self.store.write,
                        "INSERT INTO mirror_messages VALUES (?, ?, ?, ?)",
                        (message.id, index, message.channel.id, sent.id),
                    )
            for old in existing[len(parts) :]:
                with suppress(discord.NotFound):
                    await webhook.delete_message(old["destination_message"])
                await asyncio.to_thread(
                    self.store.write,
                    "DELETE FROM mirror_messages WHERE source_message=? AND part=?",
                    (message.id, old["part"]),
                )
            return True
        finally:
            for file in files:
                file.close()

    async def mark_deleted(self, message_id):
        rows = await asyncio.to_thread(self.store.messages, message_id)
        for row in rows:
            channel = await asyncio.to_thread(self.store.channel, row["source_channel"])
            webhook = await self.webhook(channel)
            try:
                copied = await webhook.fetch_message(row["destination_message"])
                embed = marker(message_id, deleted=True)
                if copied.embeds and copied.embeds[0].type == "rich":
                    embed.description = copied.embeds[0].description
                # Sin content/attachments: conserva texto y archivos existentes.
                await webhook.edit_message(
                    row["destination_message"], embed=embed, allowed_mentions=discord.AllowedMentions.none()
                )
            except discord.NotFound:
                continue


async def setup(bot):
    await bot.add_cog(MirrorCog(bot))
