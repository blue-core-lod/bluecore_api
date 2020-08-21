import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import jwt from 'express-jwt'
import jwksRsa from 'jwks-rsa'
import connect from './mongo.js'
import resourcesRouter from './endpoints/resources.js'

const app = express()

const cognitoUserPoolId = process.env.COGNITO_USER_POOL_ID || 'us-west-2_CGd9Wq136'
const awsRegion = process.env.AWS_REGION || 'us-west-2'
// This allows turning off authentication, e.g., during migration.
const noAuth = process.env.NO_AUTH === 'true'

// Increase the allowed payload size.
app.use(express.json({limit: '1mb'}))

// CORS should probably be tightened down.
app.use(cors({exposedHeaders: 'Location'}))
app.options('*', cors())
app.use(helmet())

// JWT
const publicKeySecret = jwksRsa.expressJwtSecret({
    cache: true,
    rateLimit: true,
    jwksUri: `https://cognito-idp.${awsRegion}.amazonaws.com/${cognitoUserPoolId}/.well-known/jwks.json`
  })

app.use(jwt({ secret: publicKeySecret, algorithms: ['RS256'] }).unless({
  method: ['GET'],
  custom: () => noAuth,
}))

// Add the db to req
// See https://closebrace.com/tutorials/2017-03-02/the-dead-simple-step-by-step-guide-for-front-end-developers-to-getting-up-and-running-with-nodejs-express-and-mongodb
app.use(function (req, res, next) {
  req.db = connect()
  next()
})

const port = process.env.PORT || 3000
app.use(function (req, res, next) {
 req.port = port
 next()
})


// In general, trying to follow https://jsonapi.org/

app.get('/', (req, res) => {
  res.send({all: "good"})
})

app.use('/repository', resourcesRouter)

export default app
