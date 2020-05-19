# Sloppy Labwork

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