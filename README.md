# Sloppy Labwork

[![PEP8](https://img.shields.io/badge/code%20style-pep8-orange.svg)](https://www.python.org/dev/peps/pep-0008/)

## Setup

This project uses [conda](https://docs.conda.io/en/latest/) to manage
dependencies during development. Initialize your enironment with:

```
conda env create -f environment.yml
```

Then activate with:

```
conda activate sloppy-labwork
```

Should the environment definition change, you can update your local
environment with:

```
conda env update -f environment.yml
```

We use a local configuration file to initialize necessary environment
variables during development. This file will not be tracked by version
control:

```
cp ./sloppy_labwork/local_environment.py-example ./sloppy_labwork/local_environment.py
```

You may update the new file to turn features on/off and update app secrets.


## Run It

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