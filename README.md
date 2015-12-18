# Coda [![Build Status](https://travis-ci.org/unt-libraries/coda.svg?branch=master)](https://travis-ci.org/unt-libraries/coda)


## Developing
To take advantage of the dev environment that is already configured, you need to have Docker(>= 1.3) and Docker Compose installed.

Install [Docker](https://docs.docker.com/installation/)

Install Docker Compose
```sh
$ pip install docker-compose
```

Clone the repository.
```sh
$ git clone https://github.com/unt-libraries/coda.git
$ cd coda
```

Create a `settings.json`.
```sh
$ cp settings.json.template settings.json
```

Warm up the MySQL database. This only needs to be done when the database container doesn't exist yet. This will take ~15 seconds once the image has been pulled.
```sh
$ docker-compose up -d db
```

Start the app and run the migrations.
```sh
# start the app
$ docker-compose up -d

# run the migrations
$ docker-compose run --rm coda ./manage.py migrate

# Optional: add a superuser in order to log in to the admin interface
$ docker-compose run --rm web ./manage.py createsuperuser
```

The code is in a volume that is shared between your workstation and the coda container, which means any edits you make on your workstation will also be reflected in the Docker container. No need to rebuild the container to pick up changes in the code.

However, if the requirements files change, it is important that you rebuild the coda image for those packages to be installed. This is something that could happen when switching between feature branches, or when pulling updates from the remote.

```sh
# stop the app
$ docker-compose stop

# remove the coda container
$ docker-compose rm coda

# rebuild the coda container
$ docker-compose build coda

# start the app
$ docker-compose up -d
```
