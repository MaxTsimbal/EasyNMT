# EasyNMT Project Status

Version: v0.9.7.1 Stable

## Working
- Persistent registration and login with SQLite
- 30-day login session
- Automatic account and plan restore after restart
- Separate XP and progress for each subject
- Completed lessons, achievements and quiz mistakes stored in SQLite
- Subject switching without losing previous progress
- OpenAI-ready assistant with demo fallback and request limits

## Database
The database is created automatically at `instance/users.db`. Existing databases are migrated on launch.

## Next
- Connect and test a real OpenAI API key
- Add password reset and email verification
- Prepare deployment configuration

SEO status: metadata, sitemap, robots.txt and Search Console verification support are ready.
Next: connect Google Search Console, request indexing, then design the EasyNMT logo and favicon.
