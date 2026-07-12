# Copy Privacy Policy

Effective date: 2026-06-13

Copy is a Discord application and bot for server utility, moderation-adjacent automation, community engagement, and server resource management.

This policy explains what data Copy processes, what it stores, and how users and server administrators can control that data.

## Data Copy Processes

Copy may process the following Discord data when it is needed to provide the bot's features:

- Discord user IDs, guild IDs, channel IDs, role IDs, message IDs, and emoji/sticker IDs.
- Server configuration entered by server administrators, such as configured channels, role mappings, vanity strings, auto-reaction trigger phrases, and emoji reaction settings.
- Member data needed for role automation, including roles, server join context, boost status, and member update events.
- Presence activity/custom status data for the vanity/status role module, only when a server has enabled that module.
- Message content, attachments, embeds, stickers, and custom emoji references for configured message automation features and user-invoked emoji/sticker tools.
- Basic operational data such as command usage errors and diagnostic logs needed to keep the bot working.

## Why Copy Processes Data

Copy processes Discord data only to provide its stated features, including:

- Creating and managing automatic threads in configured channels.
- Running counting channels and validating normal numeric messages.
- Adding automatic reactions to configured trigger words or phrases.
- Copying or creating emojis and stickers when an authorized user invokes the relevant command.
- Assigning or removing configured roles for vanity/custom status, server tag, and boost-related workflows.
- Showing server, role, user, boost, audit-log, and permission information to authorized users.
- Maintaining server configuration and troubleshooting the bot.

## Data Copy Stores

Copy stores only the configuration and state needed to operate the bot, such as:

- Guild IDs, channel IDs, role IDs, and feature settings.
- Auto-reaction trigger phrases and configured emoji reactions entered by server staff.
- Counting state, such as the current number and last user ID for a configured counting channel.
- Vanity/status role configuration, such as vanity strings, role IDs, channel IDs, and notification settings.
- Boost-role and clan-tag role configuration.
- Bot owner/admin configuration and bot presence presets.

Copy does not store raw message bodies as a message archive. Copy does not store raw presence history, online/offline history, device/client status history, or user activity history.

## Message Content

When Copy reads message content, it is for a configured feature or user-invoked action. For example, Copy may read a message in a configured counting channel to validate the next number, read a configured channel to create an automatic thread, or read a message to apply a configured automatic reaction.

Message content is processed transiently and is not stored as a searchable log or message history.

## Presence Data

Copy uses presence data only for the vanity/status role feature. When enabled by a server administrator, Copy checks whether a member's current custom status/activity contains a configured vanity string so it can add or remove the configured role.

Copy does not store raw presence updates or presence history.

## Attachments And Files

For emoji and sticker tools, Copy may download an attachment or Discord CDN file only when an authorized user invokes a command to create or copy an emoji/sticker. The file is used to complete that requested action and is not stored as a file archive by Copy.

## Machine Learning And Advertising

Copy does not use message content, presence data, attachments, or other Discord API data to train machine-learning or AI models.

Copy does not sell Discord API data, does not disclose it to data brokers or advertising networks, and does not use it for targeted advertising.

## User And Admin Controls

Server administrators can disable Copy features by removing the relevant configuration, using reset/remove commands, changing channel permissions, or removing the bot from the server.

Users can avoid optional configured automation channels. For vanity/status roles, users opt in by placing the configured text in their custom status and can opt out by removing that text or clearing their custom status.

## Data Retention

Configuration data is retained while the bot is installed and the feature remains configured. Server administrators can remove feature configuration through the bot's commands. If Copy leaves a server or a feature is reset, the related configuration can be removed.

Transient message content and presence data are discarded after the feature action is completed.

Operational logs are retained only as needed for security, debugging, and reliability.

## Security

Copy limits access to administrative features with Discord permissions and owner-only checks where applicable. Bot credentials are not public and should never be shared with users.

## Contact

For privacy questions, support requests, or data deletion requests, contact the application owner through the public support channel listed for Copy or through the Discord account/team that owns the application.

Application ID: 1392382340940038174
