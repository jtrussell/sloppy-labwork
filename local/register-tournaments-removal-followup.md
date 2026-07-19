# Manual follow-up: `register` + `tournaments` app removal

The code changes removing the `register` and `tournaments` Django apps are
complete. The steps below must be done by hand, roughly in this order.

## 1. Back up production data (before anything else)

- [ ] `heroku pg:backups:capture`
- The following tables will be permanently dropped:
  - `register_deckregistration`
  - `tournaments_tournament`
  - `tournaments_tournamentformat`
  - `tournaments_tournamentregistration`
  - `tournaments_tournamentregistration_decks` (M2M)

## 2. Drop the tables (BEFORE deploying the code removal)

Run these against production while the old release (with the migration files)
is still current:

- [ ] `heroku run python manage.py migrate register zero`
- [ ] `heroku run python manage.py migrate tournaments zero`

This drops the tables and clears the apps' rows from `django_migrations`.
If the code is deployed first, the migration files are gone and the tables
will have to be dropped with manual SQL instead.

## 3. Deploy the code removal

- [ ] Deploy the branch/commit containing the app removal.
- Note: the deploy and the config var removal in step 4 must land around the
  same time — the old code hard-requires the vars (`os.environ[...]`), the new
  code no longer reads them. Removing vars first crashes the old release;
  removing them after is harmless. Do step 4 after the deploy.

## 4. Remove Heroku config vars (after deploy)

- [ ] `heroku config:unset FT_USE_REGISTER`
- [ ] `heroku config:unset FT_USE_EVENTS`
- [ ] `heroku config:unset MAX_UPLOADS_PER_DAY`
- [ ] `heroku config:unset AWS_S3_BUCKET_VERIFICATION_PHOTOS_BUCKET`
- [ ] If a `REGISTER_VERIFIER_EMAIL` config var exists in Heroku, unset it too
      (it was only referenced in the local env example, but may still be set).

## 5. Post-deploy cleanup

- [ ] Delete stale content types:
      `heroku run python manage.py remove_stale_contenttypes`
      (removes the orphaned `ContentType` rows for the deleted models; admin
      log entries referencing them are cascade-deleted).
- [ ] Decide what to do with the S3 verification-photos bucket (the one that
      was in `AWS_S3_BUCKET_VERIFICATION_PHOTOS_BUCKET`) — it is now orphaned.
      Archive or delete it, and trim the IAM policy if it granted access to
      that bucket specifically.

## 6. Local dev environments

- [ ] Update your local `local_environment.py` to match the new
      `local_environment.py-example` (remove `MAX_UPLOADS_PER_DAY`,
      `AWS_S3_BUCKET_VERIFICATION_PHOTOS_BUCKET`, `REGISTER_VERIFIER_EMAIL`,
      `FT_USE_REGISTER`, `FT_USE_EVENTS`).
- [ ] Local `db.sqlite3` databases still contain the old tables; either
      recreate the database or run the `migrate ... zero` commands locally
      before pulling the change if you care about keeping it tidy.
