import fs from "fs"
import monk from "monk"

const dbUsername = process.env.MONGODB_USERNAME || "sinopia"
const dbPassword = process.env.MONGODB_PASSWORD || "sekret"
const dbName = process.env.MONGODB_DB || "sinopia_repository"
const dbHost = process.env.MONGODB_HOST || "localhost"
const dbPort = process.env.MONGODB_PORT || "27017"
const isAws = process.env.MONGODB_IS_AWS === "true"

let db

const connect = () => {
  if (!db) db = isAws ? awsConnect() : mongoConnect()
  return db
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
