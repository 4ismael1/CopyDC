# Discord Privileged Intents Review Draft

Application: Copy
Application ID: 1392382340940038174
Prepared date: 2026-06-13

Important before submitting:
- Do not submit with a dead Privacy Policy URL. The bot currently references `https://copy.tyr.lat/privacy` and `https://copy.tyr.lat/terms`, but both failed DNS resolution during review from this workspace on 2026-06-13.
- Publish `PRIVACY.md` and `TERMS.md` somewhere public first, then configure those URLs in the Discord Developer Portal and in the bot help links.
- For the evidence fields, add at least one public short video or screenshots showing the exact feature in a real Discord server. GitHub and Top.gg links help, but Discord explicitly asks for screenshots/videos.

## Recommended Strategy

Request:
- Guild Presences: Yes.
- Message Content: Yes.

Do not frame Message Content as "we need prefix commands." Discord already denied that reason and recommends slash commands or mentions for command routing. The strongest case is that Copy has event-driven features that operate on normal user messages where no slash command or interaction is fired.

## Application Details

### Field: What does your application do?

Paste this:

```text
Copy is a Discord utility and community-management bot for Spanish and English servers. It helps server administrators automate recurring community workflows and manage server resources through slash commands, hybrid commands, and limited event-driven automation.

The main user-facing features are:

1. Emoji and sticker utilities: authorized server staff can copy custom emojis/stickers or create server expressions from existing Discord messages and attachments.
2. Automatic threads: server staff can configure channels where Copy automatically creates a discussion thread under qualifying text or media posts.
3. Counting channels: server staff can configure a counting channel where members participate by sending normal numeric messages. Copy validates the next number, prevents the same member from counting twice in a row, reacts to valid/invalid entries, and resets the count on mistakes.
4. Automatic reactions: server staff can configure trigger words or phrases and emojis. When a normal message in that server matches a configured trigger, Copy adds the configured reactions.
5. Vanity/status roles: server staff can configure vanity text such as a server invite or community phrase. When a member voluntarily places that text in their Discord custom status, Copy grants a configured role and can send a configurable notification. When the member removes the vanity text, Copy removes the role.
6. Server tag / clan tag roles and boost roles: Copy can grant or remove configured roles when members change relevant server/member state, including boost-linked roles that are removed when a member stops boosting.
7. Information and admin tools: Copy provides user/server/role information, boost status, audit-log lookup for staff, permission inspection, health checks, and owner-only diagnostics.

Copy uses the minimum privileged data needed for these features. Raw message content and raw presence/activity data are processed transiently for the configured feature and are not stored as message logs or presence histories. The database stores server configuration such as guild IDs, channel IDs, role IDs, configured trigger phrases, counting state, configured vanity codes, and bot settings. Copy does not sell data, does not use data for advertising, and does not use message content or presence data to train machine-learning or AI models.

Public bot listing: https://top.gg/bot/1392382340940038174
Source repository: https://github.com/4ismael1/CopyDC
Privacy Policy: <PASTE_WORKING_PUBLIC_PRIVACY_URL>
Terms: <PASTE_WORKING_PUBLIC_TERMS_URL>
```

### Field: Do you have a public Privacy Policy that informs users about data use?

Recommended answer:

```text
Yes
```

Only select Yes after publishing a working URL. If the current `copy.tyr.lat` domain is still down, use a GitHub Pages page, a documentation site, or another stable public URL.

## Guild Presences Intent

### Field: Why do you need the Guild Presence Intent?

Paste this:

```text
Copy needs the Guild Presences intent for its server-configurable vanity/status role system.

This feature is user-facing and works as follows:

1. A server administrator enables the vanity role module for their server.
2. The administrator configures one or more accepted vanity strings, for example a server invite, brand phrase, or community vanity text, and maps each string to a Discord role.
3. A member voluntarily adds that text to their Discord custom status.
4. Copy receives the member's PRESENCE_UPDATE event and reads only the member's current activities/custom status for that configured server.
5. If the configured vanity text is present, Copy grants the configured role and optionally sends the server's configured notification embed.
6. If the member removes the vanity text, Copy removes the configured vanity role and optionally sends the configured removal notification.

This cannot be replaced by slash commands, buttons, modals, or REST lookups because a user's current custom status/activity is presence data and is only available through real-time presence updates. A slash command would require the user to manually claim the role, but it would not verify that the vanity text is currently present and would not automatically remove the role when the status changes. The purpose of the feature is real-time role synchronization based on the member's live custom status.

Copy limits this use to servers where administrators have explicitly configured the vanity module. The bot ignores bot users, ignores guilds with no vanity configuration, and does not store raw presence updates, online/offline history, device/client status, or activity history. The only stored data is server configuration such as guild ID, role ID, channel ID, configured vanity strings, and notification settings. Presence data is processed in memory only to decide whether to add or remove the configured role.
```

### Field: Provide links to screenshots/videos showing your use case.

Use this structure, but replace placeholders with real public evidence:

```text
Short demo video showing the feature end to end:
<PASTE_PUBLIC_VIDEO_URL>

Screenshots:
1. Admin configuring `/vanity add` with a vanity string and role: <PASTE_SCREENSHOT_URL>
2. Member adding the configured vanity text to their Discord custom status: <PASTE_SCREENSHOT_URL>
3. Copy granting the role and sending the configured notification: <PASTE_SCREENSHOT_URL>
4. Member removing the vanity text and Copy removing the role: <PASTE_SCREENSHOT_URL>

Public listing describing the vanity role system:
https://top.gg/bot/1392382340940038174

Source implementation:
https://github.com/4ismael1/CopyDC/blob/main/modules/vanity_cog.py
https://github.com/4ismael1/CopyDC/blob/main/modules/vanity_slash_cog.py
```

### Field: Can users opt out of tracking of their presence data?

Recommended answer:

```text
Yes
```

If a text explanation appears, paste:

```text
Members opt into the vanity role behavior by voluntarily placing the configured vanity text in their custom status. They can opt out at any time by removing that text or clearing their custom status. Server administrators can also disable the vanity module, remove configured vanity strings, or remove the bot from the server. Copy does not store presence history.
```

### Field: Are you storing user activity/presence data outside Discord?

Recommended answer:

```text
No
```

If a text explanation appears, paste:

```text
No. Copy does not store raw presence updates, online/offline status, device/client status, or activity history outside Discord. It only stores server configuration for the vanity role module, such as guild IDs, role IDs, channel IDs, configured vanity strings, and notification settings. The live custom status/activity is processed in memory to add or remove a configured role, then discarded.
```

## Message Content Intent

### Field: Can users opt out of tracking of message content data?

Recommended answer:

```text
Yes
```

If a text explanation appears, paste:

```text
Copy's message-content features are opt-in at the server/channel level and controlled by server staff. Counting, automatic threads, and automatic reactions only run where server administrators configure them. Users can avoid participating in configured automation channels, and server administrators can disable each module or remove the bot. Copy does not create a searchable message log and does not store raw message bodies.
```

If Discord requires a strict per-user answer instead of server/channel controls, answer `No` and explain:

```text
There is no per-user opt-out for messages sent in channels where server staff have enabled a message-content automation module, because reading the message is the feature being provided in that channel. The controls are channel/server-level: administrators choose where the module runs and can disable it at any time. Copy does not store raw message bodies.
```

### Field: Are you storing message content data outside Discord?

Recommended answer:

```text
No
```

If a text explanation appears, paste:

```text
No. Copy processes message content transiently for configured features and does not store raw message bodies, attachments, embeds, or a message history outside Discord.

The database stores only configuration/state needed for the feature, such as guild IDs, channel IDs, role IDs, configured auto-reaction trigger phrases entered by server staff, configured emojis, and counting state such as current number and last user ID. For the expression tools, files are only downloaded when an authorized user invokes the command to create an emoji/sticker, and the file is sent back to Discord as the requested server expression rather than stored as a message archive.
```

### Field: Will message content data be used to train ML/AI models?

Recommended answer:

```text
No
```

If a text explanation appears, paste:

```text
No. Copy does not use message content, attachments, embeds, components, polls, or derived message data to train machine-learning or AI models. It does not provide message content to third-party AI systems.
```

### Field: Why do you need the Message Content Intent?

Paste this:

```text
Copy needs the Message Content intent for event-driven, user-facing features that operate on normal Discord messages. These are not command-routing use cases and cannot be replaced by slash command options, because the bot must react to ordinary messages when users send them.

The required features are:

1. Counting channels
Server administrators configure a channel as a counting channel. Members participate by sending normal messages containing the next number. Copy must read each message's text in that configured channel to determine whether it is the expected integer, prevent the same member from counting twice in a row, react to valid entries, remove non-number interruptions, and reset the game on mistakes. A slash command cannot replace this because the gameplay is intentionally based on normal channel messages and requires real-time validation of every message in that channel.

2. Automatic reactions
Server administrators configure trigger words or phrases and one or more emoji reactions. Copy must read normal messages as they are sent, compare the text with the configured trigger phrases, and add the configured reactions to matching messages. This cannot be replaced by application command options because users are not invoking the bot; the feature is automatic moderation/community engagement based on normal message text in the server.

3. Automatic thread creation
Server administrators configure channels where Copy automatically creates discussion threads under qualifying posts. Depending on the configured mode, Copy needs to know whether a message contains text and/or media attachments so it can create a thread for the correct posts and avoid creating threads for empty or irrelevant messages. Application commands cannot replace this because the bot must respond to regular posts sent by users in the configured channel.

4. Emoji/sticker expression utilities when invoked by an authorized user
Authorized staff can reply to an existing message and ask Copy to copy or extract a custom emoji/sticker or create an expression from a message attachment. The bot needs access to the referenced message's content/attachments for that user-initiated action. This is limited to staff-invoked utility commands and does not create a message archive.

Copy already supports slash/hybrid commands for many setup flows, and the requested Message Content access is not for continuing legacy prefix command routing by itself. The access is needed for passive, real-time features where no slash command, button, modal, or mention event is generated. Copy processes message content in memory, only for configured modules, and does not store raw message bodies or message history outside Discord.
```

### Field: Provide links to screenshots/videos showing your use case.

Use this structure, replacing placeholders:

```text
Short demo video showing Message Content use cases:
<PASTE_PUBLIC_VIDEO_URL>

Screenshots:
1. Counting channel configured with `/counting set`: <PASTE_SCREENSHOT_URL>
2. Members sending normal number messages and Copy validating/reacting/resetting: <PASTE_SCREENSHOT_URL>
3. Auto-reaction configured with `/react add`: <PASTE_SCREENSHOT_URL>
4. Normal user message matching the trigger and Copy adding reactions automatically: <PASTE_SCREENSHOT_URL>
5. Auto-thread channel configured with `/thread add`: <PASTE_SCREENSHOT_URL>
6. User posting normal text/media and Copy creating the thread automatically: <PASTE_SCREENSHOT_URL>

Public listing describing these features:
https://top.gg/bot/1392382340940038174

Source implementation:
https://github.com/4ismael1/CopyDC/blob/main/modules/counting_cog.py
https://github.com/4ismael1/CopyDC/blob/main/modules/auto_react_cog.py
https://github.com/4ismael1/CopyDC/blob/main/modules/threads_cog.py
https://github.com/4ismael1/CopyDC/blob/main/modules/expression_cog.py
```

## Evidence To Capture Before Submitting

Record one 60-90 second video for Presence:
- Open a test server.
- Run `/vanity add codigo:<your vanity text> rol:@Role`.
- Show the member has no role.
- Change member custom status to include the configured text.
- Show Copy grants the role and sends the notification.
- Remove the custom status.
- Show Copy removes the role.

Record one 60-90 second video for Message Content:
- Run `/counting set`.
- Send normal messages `1`, `2`, wrong number; show reactions/reset.
- Run `/react add trigger_phrase:<word> emojis:<emoji>`.
- Send a normal message containing the word; show automatic reaction.
- Run `/thread add` on a channel.
- Send a normal text/media post; show automatic thread creation.

Avoid saying:
- "We need message content for prefix commands."
- "The bot needs all messages."
- "Presence is for statistics/analytics."
- "We store activity/message history."

Use instead:
- "Configured channels/modules only."
- "Transient processing in memory."
- "No raw message log."
- "No presence history."
- "No ML/AI training."
- "No sale/advertising use."

## Source Notes

Discord's current docs say apps over 10,000 users need privileged intent review and that requesting intents that are not clearly needed can hurt the submission:
https://docs.discord.com/developers/gateway/getting-started-with-privileged-intent-review

Discord's docs define Guild Presences as access to online/offline, activities, and client status, and note that presence data is not available through other means:
https://docs.discord.com/developers/gateway/you-might-not-need-a-privileged-intent

Discord's Gateway docs define Message Content as access to content, embeds, attachments, components, and poll fields, with exceptions for DMs, mentions, bot-authored messages, and message context menu commands:
https://docs.discord.com/developers/events/gateway
