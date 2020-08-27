import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import jwt from 'express-jwt'
import connect from './mongo.js'
import jwtConfig from './jwt.js'
import resourcesRouter from './endpoints/resources.js'
import groupsRouter from './endpoints/groups.js'

const app = express()

// This allows turning off authentication, e.g., during migration.
const noAuth = process.env.NO_AUTH === 'true'

// Increase the allowed payload size.
app.use(express.json({limit: '1mb'}))

// CORS should probably be tightened down.
app.use(cors({exposedHeaders: 'Location'}))
app.options('*', cors())
app.use(helmet())

// JWT
app.use(jwt(jwtConfig()).unless({
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
app.use('/groups', groupsRouter)

export default app
