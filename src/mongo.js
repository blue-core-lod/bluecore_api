import fs from "fs"
import monk from "monk"

const dbUsername = process.env.MONGODB_USERNAME || "sinopia"
const dbPassword = process.env.MONGODB_PASSWORD || "sekret"
const dbName = process.env.MONGODB_DB || "sinopia_repository"
const dbHost = process.env.MONGODB_HOST || "localhost"
const dbPort = process.env.MONGODB_PORT || "27017"
const isAws = process.env.MONGODB_IS_AWS === "true"

let db

// Add the db to req
// See https://closebrace.com/tutorials/2017-03-02/the-dead-simple-step-by-step-guide-for-front-end-developers-to-getting-up-and-running-with-nodejs-express-and-mongodb
const connect = (req, res, next) => {
  if (!db) db = isAws ? awsConnect() : mongoConnect()
  req.db = db
  next()
}

const awsConnect = () => {
  console.log(`connecting to DocDB at ${dbHost}`)
  const ca = [fs.readFileSync("rds-combined-ca-bundle.pem")]

  return monk(
    `mongodb://${dbUsername}:${dbPassword}@${dbHost}:${dbPort}/${dbName}?ssl=true&replicaSet=rs0&readPreference=secondaryPreferred&retryWrites=false`,
    {
      sslValidate: true,
      sslCA: ca,
      useNewUrlParser: true,
    }
  )
}

const mongoConnect = () => {
  console.log(`connecting to Mongo at ${dbHost}`)
  return monk(
    `mongodb://${dbUsername}:${dbPassword}@${dbHost}:${dbPort}/${dbName}`,
    { useUnifiedTopology: true }
  )
}

export default connect
