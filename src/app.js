import express from "express"
import cors from "cors"
import helmet from "helmet"
import Honeybadger from "@honeybadger-io/js"
import jwt from "express-jwt"
import * as OpenApiValidator from "express-openapi-validator"
import jwtConfig from "./jwt.js"
import resourcesRouter from "./endpoints/resources.js"
import groupsRouter from "./endpoints/groups.js"
import marcRouter from "./endpoints/marc.js"
import metricsRouter from "./endpoints/metrics.js"
import transferRouter from "./endpoints/transfer.js"
import usersRouter from "./endpoints/users.js"
import helperRouter from "./endpoints/helpers.js"
import {
  errorHandler,
  mongoErrorAdapter,
  s3ErrorAdapter,
  openApiValidatorErrorHandler,
  jwtErrorAdapter,
} from "./error.js"

const isProduction = process.env.NODE_ENV === "production"

Honeybadger.configure({
  apiKey: process.env.HONEYBADGER_API_KEY,
  environment: process.env.HONEYBADGER_ENV,
})

const app = express()

// Handle CORS before openapi validation.
app.use(cors({ exposedHeaders: ["Location", "Content-Location"] }))
app.options("*", cors())

// Increase the allowed payload size.
// Required before OpenApiValidator.
app.use(express.json({ limit: "1mb" }))
app.use(express.text())

app.use(
  OpenApiValidator.middleware({
    apiSpec: "./openapi.yml",
    validateApiSpec: !isProduction,
    validateResponses: !isProduction,
  })
)

app.use(function (req, res, next) {
  if (!isProduction) console.log(`${req.method} ${req.url}`)
  next()
})

app.use(helmet())

// JWT
// This allows turning off authentication, e.g., during migration.
const noAuth = process.env.NO_AUTH === "true"

app.use(
  jwt(jwtConfig()).unless({
    method: ["GET"],
    custom: () => noAuth,
  })
)

const port = process.env.PORT || 3000
app.use(function (req, res, next) {
  req.port = port
  next()
})

// In general, trying to follow https://jsonapi.org/

app.get("/", (req, res) => {
  res.send({ all: "good" })
})

app.use("/resource", resourcesRouter)
app.use("/marc", marcRouter)
app.use("/groups", groupsRouter)
app.use("/transfer", transferRouter)
app.use("/user", usersRouter)
app.use("/metrics", metricsRouter)
app.use("/helpers", helperRouter)

// Error handlers
app.use((err, req, res, next) => {
  console.error(`Error for ${req.originalUrl}`, err)
  next(err)
})
app.use(jwtErrorAdapter)
app.use(mongoErrorAdapter)
app.use(s3ErrorAdapter)
app.use(openApiValidatorErrorHandler)
app.use(errorHandler)

export default app
