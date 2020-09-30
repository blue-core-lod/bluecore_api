[![CircleCI](https://circleci.com/gh/LD4P/sinopia_api.svg?style=svg)](https://circleci.com/gh/LD4P/sinopia_api)
[![Docker image](https://images.microbadger.com/badges/image/ld4p/sinopia_api.svg)](https://microbadger.com/images/ld4p/sinopia_api "Get your own image badge on microbadger.com")
[![OpenAPI Validator](http://validator.swagger.io/validator?url=https://raw.githubusercontent.com/LD4P/sinopia_api/master/openapi.yml)](http://validator.swagger.io/validator/debug?url=https://raw.githubusercontent.com/LD4P/sinopia_api/master/openapi.yml)

# Sinopia API

API for managing Sinopia resources atop the Mongo / AWS DocumentDB platform.

## Installation

### Prerequisites

* [node.js](https://nodejs.org/en/download/) JavaScript runtime (>=14 is recommended)
* [npm](https://www.npmjs.com/) JavaScript package manager
* [Docker](https://www.docker.com/)

You can use the ["n"](https://www.npmjs.com/package/n) node package management to manage multiple version of node.

### Installation instructions

1.  Run `npm init`, and follow the instructions that appear.
2.  Get latest npm: `npm install -g npm@latest`
3.  Run `npm install`. This installs everything needed for the build to run successfully.
4.  Run `docker-compose pull` to pull down all images.

## Running the application
To start all of the supporting services (Mongo, etc.):
`docker-compose up -d`

To start the Express web server and run the application at [http://localhost:3000](http://localhost:3000):
`npm run dev-start`

This is in development mode and code changes will immediately be loaded without having to restart the server.

If you are working on the MARC endpoints, supply the AWS credentials:
`AWS_ACCESS_KEY_ID=AKIAWCX4L27WVC12345 AWS_SECRET_ACCESS_KEY=eSxHrLXdBUZSVNWvRLaOdq771rtgoj1i12345 npm run dev-start`

## Developers

### Linter for JavaScript
To run eslint:
`npm run eslint`

To automatically fix problems (where possible):
`npm run eslint-fix`

### Monitoring Mongo
Mongo Express is available for monitoring local Mongo at http://localhost:8082.
