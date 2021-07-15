release: python manage.py migrate
web: bin/start-nginx gunicorn -c config/gunicorn.conf.py --pythonpath src swindle.wsgi