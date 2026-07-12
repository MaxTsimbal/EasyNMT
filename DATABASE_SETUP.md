# EasyNMT database

EasyNMT automatically creates `instance/users.db` on first launch.

Stored data:
- registered accounts and secure password hashes;
- selected goal, subject and preparation time;
- XP, progress, streak and last activity;
- completed lessons and best quiz results;
- achievements;
- quiz mistakes;
- OpenAI daily usage count.

## Updating an existing EasyNMT folder
To keep accounts from an older version, copy the old file:

`instance/users.db`

into the `instance` folder of this version before launch. The app will add missing tables automatically without deleting existing accounts.

Do not upload `users.db` publicly because it contains account data.
