# Sloppy Labwork

[![PEP8](https://img.shields.io/badge/code%20style-pep8-orange.svg)](https://www.python.org/dev/peps/pep-0008/)

## Setup

### Docker

You want to work with Docker? Nice! You can skip all the Python setup steps
below. We just have to make sure our local configuration files get created.
Git ignores this file (it contains secrets), but we do keep a handy template
around that will get you off the ground:

```
cp ./sloppy_labwork/local_environment.py-example ./sloppy_labwork/local_environment.py
```

### Ye Olde Python

We recommend using a virtual environment for your project, our dependencies
listed in `requirements.txt` and the version of python used in production is given in `runtime.txt`.

Install the dependencies listed in our requirements file and then ensure you
have a local settings file prepared:

```
cp ./sloppy_labwork/local_environment.py-example ./sloppy_labwork/local_environment.py
```

You may update the this local environment file to turn features on/off and update app secrets.


## Run It

### Docker

Start the app with:

```
docker-compose up
```

And you should be good to go!

Note that the first time you run the app, as well as any time you wish to
apply database migrations, you'll have to do so with the following command:

```
docker-compose exec web python manage.py migrate
```

### Python

Once setup is compelete, you can apply database migrations with:

```
python manage.py migrate
```

And run the development server with:

```
python manage.py runserver
```


## Signing In

In production, we only support signing in via 3rd party authentication
providers. The most convenient way to authenticate during development is by
using the Django Admin at
[http://localhost:8000/admin](http://localhost:8000/admin).

Alternatively, you may enter a `SocialApp` record in the DB for your own
Discord app.