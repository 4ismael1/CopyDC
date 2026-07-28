from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

import database as db
from command_utils import maybe_defer, send_response
from localization import get_language, translate, translate_language

log = logging.getLogger("bot")
MAX_CONFIGURED_GAMES = 20
MAX_VISIBLE_PLAYERS_PER_GAME = 30


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def playing_activity_names(member: discord.Member) -> set[str]:
    """Devuelve nombres normalizados de actividades de tipo Playing."""
    return {
        activity.name.casefold().strip()
        for activity in member.activities
        if activity.type is discord.ActivityType.playing and getattr(activity, "name", None)
    }


def matching_lfg_game(member: discord.Member, games: list[Any]):
    active_names = playing_activity_names(member)
    return next(
        (game for game in games if game["activity_name"].casefold().strip() in active_names),
        None,
    )


class LFGDashboardView(discord.ui.View):
    def __init__(self, cog: LiveLFGCog, language: str = "en"):
        super().__init__(timeout=None)
        self.cog = cog
        self.enroll.label = translate_language(language, "lfg.button.enroll")
        self.leave.label = translate_language(language, "lfg.button.leave")

    @discord.ui.button(
        label="Participar automáticamente",
        style=discord.ButtonStyle.success,
        custom_id="copy:lfg:enroll",
    )
    async def enroll(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.set_enrollment_from_interaction(interaction, enrolled=True)

    @discord.ui.button(
        label="Salir del LFG",
        style=discord.ButtonStyle.secondary,
        custom_id="copy:lfg:leave",
    )
    async def leave(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.set_enrollment_from_interaction(interaction, enrolled=False)


class LiveLFGCog(commands.Cog):
    """Matchmaking voluntario activado por la actividad Playing de Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._member_locks: dict[tuple[int, int], asyncio.Lock] = {}
        self._dashboard_tasks: dict[int, asyncio.Task] = {}
        self.dashboard_view = LFGDashboardView(self)
        self.bot.add_view(self.dashboard_view)
        self.reconcile_lfg_state.start()

    def cog_unload(self):
        self.reconcile_lfg_state.cancel()
        for task in self._dashboard_tasks.values():
            task.cancel()

    def _member_lock(self, guild_id: int, user_id: int) -> asyncio.Lock:
        key = (guild_id, user_id)
        lock = self._member_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._member_locks[key] = lock
        return lock

    @staticmethod
    def _manageable_role(guild: discord.Guild, role: discord.Role) -> bool:
        me = guild.me
        return bool(me and not role.is_default() and not role.managed and role < me.top_role)

    async def _remove_tracked_role(self, member: discord.Member, assignment: Any | None):
        if assignment is None:
            return
        role = member.guild.get_role(assignment["role_id"])
        if role is not None and role in member.roles and self._manageable_role(member.guild, role):
            try:
                await member.remove_roles(role, reason="Live LFG activity ended")
            except discord.HTTPException as exc:
                log.warning(
                    "No se pudo retirar rol LFG %s a %s en %s: %s",
                    role.id,
                    member.id,
                    member.guild.id,
                    exc,
                )

    async def process_member(self, member: discord.Member) -> bool:
        """Reconcilia un miembro y retorna True si cambió el panel."""
        if member.bot:
            return False
        async with self._member_lock(member.guild.id, member.id):
            settings, enrolled, games, current = await asyncio.gather(
                asyncio.to_thread(db.get_lfg_settings, member.guild.id),
                asyncio.to_thread(db.is_lfg_enrolled, member.guild.id, member.id),
                asyncio.to_thread(db.get_lfg_games, member.guild.id),
                asyncio.to_thread(db.get_lfg_assignment, member.guild.id, member.id),
            )
            if settings is None:
                return False

            matched = matching_lfg_game(member, games) if enrolled else None
            if matched is None:
                if current is None:
                    return False
                await self._remove_tracked_role(member, current)
                await asyncio.to_thread(db.delete_lfg_assignment, member.guild.id, member.id)
                return True

            new_role = member.guild.get_role(matched["role_id"])
            if new_role is None or not self._manageable_role(member.guild, new_role):
                log.warning(
                    "Rol LFG no disponible o inmanejable en guild=%s role=%s",
                    member.guild.id,
                    matched["role_id"],
                )
                if current is not None:
                    await self._remove_tracked_role(member, current)
                    await asyncio.to_thread(db.delete_lfg_assignment, member.guild.id, member.id)
                    return True
                return False

            same_assignment = (
                current is not None
                and current["game_id"] == matched["game_id"]
                and current["role_id"] == new_role.id
            )
            if same_assignment:
                if new_role not in member.roles:
                    try:
                        await member.add_roles(new_role, reason="Live LFG active game")
                    except discord.HTTPException as exc:
                        log.warning("No se pudo restaurar rol LFG a %s: %s", member.id, exc)
                return False

            await self._remove_tracked_role(member, current)
            if current is not None:
                await asyncio.to_thread(db.delete_lfg_assignment, member.guild.id, member.id)
            if new_role not in member.roles:
                try:
                    await member.add_roles(new_role, reason="Live LFG active game")
                except discord.HTTPException as exc:
                    log.warning("No se pudo asignar rol LFG a %s: %s", member.id, exc)
                    return current is not None
            await asyncio.to_thread(
                db.set_lfg_assignment,
                member.guild.id,
                member.id,
                matched["game_id"],
                new_role.id,
                utc_now_iso(),
            )
            return True

    def schedule_dashboard_update(self, guild_id: int):
        running = self._dashboard_tasks.get(guild_id)
        if running is not None and not running.done():
            return
        self._dashboard_tasks[guild_id] = asyncio.create_task(
            self._delayed_dashboard_update(guild_id),
            name=f"lfg-dashboard-{guild_id}",
        )

    async def _delayed_dashboard_update(self, guild_id: int):
        await asyncio.sleep(1.5)
        try:
            await self.update_dashboard(guild_id)
        except Exception:
            log.exception("No se pudo actualizar el panel LFG de guild=%s", guild_id)

    async def update_dashboard(self, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        settings, games, assignments = await asyncio.gather(
            asyncio.to_thread(db.get_lfg_settings, guild_id),
            asyncio.to_thread(db.get_lfg_games, guild_id),
            asyncio.to_thread(db.get_lfg_assignments, guild_id),
        )
        if settings is None:
            return
        channel = guild.get_channel(settings["dashboard_channel_id"])
        if not isinstance(channel, discord.TextChannel):
            return

        grouped: dict[int, list[int]] = {game["game_id"]: [] for game in games}
        for assignment in assignments:
            if guild.get_member(assignment["user_id"]) is not None:
                grouped.setdefault(assignment["game_id"], []).append(assignment["user_id"])

        embed = discord.Embed(
            title=translate(guild, "lfg.dashboard.title"),
            description=translate(guild, "lfg.dashboard.description"),
            color=0x5865F2,
            timestamp=datetime.now(UTC),
        )
        total = 0
        if not games:
            embed.add_field(
                name=translate(guild, "lfg.dashboard.empty_name"),
                value=translate(guild, "lfg.dashboard.empty_value"),
                inline=False,
            )
        for game in games:
            user_ids = grouped.get(game["game_id"], [])
            total += len(user_ids)
            visible = user_ids[:MAX_VISIBLE_PLAYERS_PER_GAME]
            value = " ".join(f"<@{user_id}>" for user_id in visible) or translate(
                guild, "lfg.dashboard.nobody"
            )
            if len(user_ids) > len(visible):
                value += "\n" + translate(
                    guild,
                    "lfg.dashboard.more",
                    count=len(user_ids) - len(visible),
                )
            embed.add_field(
                name=f"{game['display_name']} · {len(user_ids)}",
                value=value,
                inline=False,
            )
        embed.set_footer(text=translate(guild, "lfg.dashboard.footer", count=total))
        localized_view = LFGDashboardView(self, get_language(guild))

        message = None
        if settings["dashboard_message_id"]:
            try:
                message = await channel.fetch_message(settings["dashboard_message_id"])
            except discord.NotFound:
                await asyncio.to_thread(db.set_lfg_dashboard_message, guild_id, None)
        if message is None:
            message = await channel.send(
                embed=embed,
                view=localized_view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await asyncio.to_thread(db.set_lfg_dashboard_message, guild_id, message.id)
        else:
            await message.edit(
                embed=embed,
                view=localized_view,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def set_enrollment_from_interaction(
        self,
        interaction: discord.Interaction,
        *,
        enrolled: bool,
    ):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                translate(interaction, "lfg.server_only"),
                ephemeral=True,
            )
            return
        if await asyncio.to_thread(db.get_lfg_settings, interaction.guild.id) is None:
            await interaction.response.send_message(
                translate(interaction, "lfg.not_configured_short"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        if enrolled:
            await asyncio.to_thread(
                db.enroll_lfg_user,
                interaction.guild.id,
                interaction.user.id,
                utc_now_iso(),
            )
            changed = await self.process_member(interaction.user)
            if changed:
                self.schedule_dashboard_update(interaction.guild.id)
            await interaction.followup.send(
                translate(interaction, "lfg.enrolled"),
                ephemeral=True,
            )
            return

        assignment = await asyncio.to_thread(
            db.unenroll_lfg_user,
            interaction.guild.id,
            interaction.user.id,
        )
        await self._remove_tracked_role(interaction.user, assignment)
        self.schedule_dashboard_update(interaction.guild.id)
        await interaction.followup.send(
            translate(interaction, "lfg.leave"),
            ephemeral=True,
        )

    @commands.Cog.listener("on_presence_update")
    async def live_activity_listener(self, before: discord.Member, after: discord.Member):
        if playing_activity_names(before) == playing_activity_names(after):
            return
        if await self.process_member(after):
            self.schedule_dashboard_update(after.guild.id)

    @commands.Cog.listener("on_member_remove")
    async def lfg_member_remove(self, member: discord.Member):
        assignment = await asyncio.to_thread(db.unenroll_lfg_user, member.guild.id, member.id)
        if assignment is not None:
            self.schedule_dashboard_update(member.guild.id)

    @commands.Cog.listener("on_copy_language_change")
    async def lfg_language_change(self, guild: discord.Guild, _: str):
        await self.update_dashboard(guild.id)

    @commands.hybrid_group(
        name="lfg",
        invoke_without_command=True,
        fallback="panel",
        description="Matchmaking automático por actividad en vivo",
    )
    @commands.guild_only()
    async def lfg(self, ctx: commands.Context):
        await send_response(
            ctx,
            translate(ctx, "lfg.help"),
            ephemeral=True,
        )

    @lfg.command(name="setup", description="Configura el canal del panel LFG")
    @app_commands.describe(channel="Canal donde se publicará el panel en vivo")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def lfg_setup(self, ctx: commands.Context, channel: discord.TextChannel):
        me = ctx.guild.me
        if me is None:
            await send_response(ctx, translate(ctx, "lfg.permissions_unresolved"), ephemeral=True)
            return
        permissions = channel.permissions_for(me)
        if not permissions.send_messages or not permissions.embed_links:
            await send_response(
                ctx,
                translate(ctx, "lfg.permissions_missing"),
                ephemeral=True,
            )
            return
        await asyncio.to_thread(db.set_lfg_settings, ctx.guild.id, channel.id)
        await maybe_defer(ctx, ephemeral=True)
        await self.update_dashboard(ctx.guild.id)
        await send_response(
            ctx,
            translate(ctx, "lfg.setup_success", channel=channel.mention),
            ephemeral=True,
        )

    @lfg.command(name="game_add", description="Añade una actividad y su rol temporal")
    @app_commands.describe(
        activity_name="Nombre exacto que Discord muestra como actividad",
        role="Rol temporal y dedicado para ese juego",
        display_name="Nombre visible en el panel (opcional)",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def lfg_game_add(
        self,
        ctx: commands.Context,
        activity_name: str,
        role: discord.Role,
        *,
        display_name: str | None = None,
    ):
        if await asyncio.to_thread(db.get_lfg_settings, ctx.guild.id) is None:
            await send_response(ctx, translate(ctx, "lfg.setup_first"), ephemeral=True)
            return
        activity_name = activity_name.strip()
        display_name = (display_name or activity_name).strip()
        if not activity_name or len(activity_name) > 80 or not display_name or len(display_name) > 80:
            await send_response(ctx, translate(ctx, "lfg.names_invalid"), ephemeral=True)
            return
        if not self._manageable_role(ctx.guild, role):
            await send_response(
                ctx,
                translate(ctx, "lfg.role_invalid"),
                ephemeral=True,
            )
            return
        existing_games = await asyncio.to_thread(db.get_lfg_games, ctx.guild.id)
        existing = next(
            (game for game in existing_games if game["activity_name"].casefold() == activity_name.casefold()),
            None,
        )
        if existing is None and len(existing_games) >= MAX_CONFIGURED_GAMES:
            await send_response(
                ctx,
                translate(ctx, "lfg.activity_limit", limit=MAX_CONFIGURED_GAMES),
                ephemeral=True,
            )
            return
        await asyncio.to_thread(
            db.upsert_lfg_game,
            ctx.guild.id,
            activity_name,
            display_name,
            role.id,
        )
        await maybe_defer(ctx, ephemeral=True)
        await self.reconcile_guild(ctx.guild)
        await self.update_dashboard(ctx.guild.id)
        await send_response(
            ctx,
            translate(
                ctx,
                "lfg.activity_added",
                activity=discord.utils.escape_markdown(activity_name),
                role=role.mention,
            ),
            ephemeral=True,
        )

    @lfg.command(name="game_remove", description="Elimina una actividad configurada")
    @app_commands.describe(activity_name="Nombre exacto configurado")
    @commands.has_permissions(manage_roles=True)
    async def lfg_game_remove(self, ctx: commands.Context, *, activity_name: str):
        game = await asyncio.to_thread(db.get_lfg_game_by_activity, ctx.guild.id, activity_name)
        if game is None:
            await send_response(ctx, translate(ctx, "lfg.activity_missing"), ephemeral=True)
            return
        assignments = await asyncio.to_thread(db.get_lfg_assignments, ctx.guild.id)
        affected = [row for row in assignments if row["game_id"] == game["game_id"]]
        for assignment in affected:
            member = ctx.guild.get_member(assignment["user_id"])
            if member is not None:
                await self._remove_tracked_role(member, assignment)
        await asyncio.to_thread(db.delete_lfg_game, ctx.guild.id, activity_name)
        await self.update_dashboard(ctx.guild.id)
        await send_response(
            ctx,
            translate(
                ctx,
                "lfg.activity_removed",
                activity=discord.utils.escape_markdown(game["display_name"]),
            ),
            ephemeral=True,
        )

    @lfg.command(name="games", description="Muestra las actividades LFG configuradas")
    async def lfg_games(self, ctx: commands.Context):
        games = await asyncio.to_thread(db.get_lfg_games, ctx.guild.id)
        if not games:
            await send_response(ctx, translate(ctx, "lfg.games.none"), ephemeral=True)
            return
        lines = [
            translate(
                ctx,
                "lfg.games.item",
                display_name=discord.utils.escape_markdown(game["display_name"]),
                activity_name=discord.utils.escape_markdown(game["activity_name"]),
                role=f"<@&{game['role_id']}>",
            )
            for game in games
        ]
        embed = discord.Embed(
            title=translate(ctx, "lfg.games.title"),
            description="\n".join(lines),
            color=0x5865F2,
        )
        await send_response(
            ctx,
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @lfg.command(name="enroll", description="Participa voluntariamente en el LFG automático")
    async def lfg_enroll(self, ctx: commands.Context):
        if await asyncio.to_thread(db.get_lfg_settings, ctx.guild.id) is None:
            await send_response(ctx, translate(ctx, "lfg.not_configured"), ephemeral=True)
            return
        await asyncio.to_thread(db.enroll_lfg_user, ctx.guild.id, ctx.author.id, utc_now_iso())
        if await self.process_member(ctx.author):
            self.schedule_dashboard_update(ctx.guild.id)
        await send_response(
            ctx,
            translate(ctx, "lfg.enrolled_command"),
            ephemeral=True,
        )

    @lfg.command(name="leave", description="Deja de participar y elimina tu estado LFG actual")
    async def lfg_leave(self, ctx: commands.Context):
        assignment = await asyncio.to_thread(db.unenroll_lfg_user, ctx.guild.id, ctx.author.id)
        await self._remove_tracked_role(ctx.author, assignment)
        self.schedule_dashboard_update(ctx.guild.id)
        await send_response(
            ctx,
            translate(ctx, "lfg.leave_command"),
            ephemeral=True,
        )

    @lfg.command(name="status", description="Consulta tu participación y actividad LFG detectada")
    async def lfg_status(self, ctx: commands.Context):
        enrolled, assignment = await asyncio.gather(
            asyncio.to_thread(db.is_lfg_enrolled, ctx.guild.id, ctx.author.id),
            asyncio.to_thread(db.get_lfg_assignment, ctx.guild.id, ctx.author.id),
        )
        if not enrolled:
            message = translate(ctx, "lfg.status.not_enrolled")
        elif assignment is None:
            message = translate(ctx, "lfg.status.enrolled_idle")
        else:
            game = next(
                (
                    row
                    for row in await asyncio.to_thread(db.get_lfg_games, ctx.guild.id)
                    if row["game_id"] == assignment["game_id"]
                ),
                None,
            )
            message = (
                translate(
                    ctx,
                    "lfg.status.active",
                    game=discord.utils.escape_markdown(game["display_name"]),
                )
                if game
                else translate(ctx, "lfg.status.updating")
            )
        await send_response(ctx, message, ephemeral=True)

    @lfg.command(name="privacy", description="Explica qué datos usa y conserva el LFG")
    async def lfg_privacy(self, ctx: commands.Context):
        await send_response(
            ctx,
            translate(ctx, "lfg.privacy"),
            ephemeral=True,
        )

    async def reconcile_guild(self, guild: discord.Guild):
        enrollments = await asyncio.to_thread(db.get_lfg_enrollments, guild.id)
        enrolled_ids = {row["user_id"] for row in enrollments}
        for user_id in enrolled_ids:
            member = guild.get_member(user_id)
            if member is not None and await self.process_member(member):
                self.schedule_dashboard_update(guild.id)

        assignments = await asyncio.to_thread(db.get_lfg_assignments, guild.id)
        for assignment in assignments:
            if assignment["user_id"] not in enrolled_ids:
                member = guild.get_member(assignment["user_id"])
                if member is not None:
                    await self._remove_tracked_role(member, assignment)
                await asyncio.to_thread(db.delete_lfg_assignment, guild.id, assignment["user_id"])

    @tasks.loop(minutes=15)
    async def reconcile_lfg_state(self):
        for guild in self.bot.guilds:
            if await asyncio.to_thread(db.get_lfg_settings, guild.id) is not None:
                await self.reconcile_guild(guild)
                await self.update_dashboard(guild.id)

    @reconcile_lfg_state.before_loop
    async def before_reconcile_lfg_state(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(LiveLFGCog(bot))
