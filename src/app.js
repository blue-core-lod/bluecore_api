import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import HoneybadgerNotifier from './honeybadger.js'
import jwt from 'express-jwt'
import connect from './mongo.js'
import jwtConfig from './jwt.js'
import resourcesRouter from './endpoints/resources.js'
import groupsRouter from './endpoints/groups.js'
import marcRouter from './endpoints/marc.js'

const app = express()

// Use *before* all other app middleware.
// See https://github.com/honeybadger-io/crywolf-node
app.use(HoneybadgerNotifier.requestHandler)

app.use(function (req, res, next) {
  if(process.env.NODE_ENV === 'development') console.log(`${req.method} ${req.url}`)
  next()
})

// Increase the allowed payload size.
app.use(express.json({limit: '1mb'}))

// CORS should probably be tightened down.
app.use(cors({exposedHeaders: [
  'Location',
  'Content-Location'
]}))
app.options('*', cors())
app.use(helmet())

// JWT
// This allows turning off authentication, e.g., during migration.
const noAuth = process.env.NO_AUTH === 'true'

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
app.use('/marc', marcRouter)
app.use('/groups', groupsRouter)

export default app
