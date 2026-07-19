# EasyNMT database

EasyNMT automatically creates `instance/users.db` on first launch.

Stored data:
- registered accounts and secure password hashes;
- selected goal, subject and preparation time;
- XP, progress, streak and last activity;
- completed lessons and best quiz results;
- achievements;
- quiz mistakes;
- quiz attempts, server-side quiz sessions and answer drafts;
- per-subject progress and lesson readiness;
- AI conversations, messages, feedback and attachment metadata;
- daily OpenAI usage and upload limits.

## Updating an existing EasyNMT folder
To keep accounts from an older version, copy the old file:

`instance/users.db`

into the `instance` folder of this version before launch. The app will add missing tables automatically without deleting existing accounts.

Do not upload `users.db` publicly because it contains account data.
