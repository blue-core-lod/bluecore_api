import MongoClient  from 'mongodb'
import fs from 'fs'

export const connect = () => {
  const dbUsername = process.env.MONGODB_USERNAME || 'sinopia'
  const dbPassword = process.env.MONGODB_PASSWORD || 'sekret'
  const dbName = process.env.MONGODB_DB || 'sinopia_repository'
  const dbHost = process.env.MONGODB_HOST || 'localhost'
  const dbPort = process.env.MONGODB_PORT || '27017'
  const isAws = process.env.MONGODB_IS_AWS === 'true'

  let connect
  if (isAws) {
    console.log(`connecting to DocDB at ${dbHost}`)
    const ca = [fs.readFileSync('rds-combined-ca-bundle.pem')]

    connect = MongoClient.connect(`mongodb://${dbUsername}:${dbPassword}@${dbHost}:${dbPort}/${dbName}?ssl=true&replicaSet=rs0&readPreference=secondaryPreferred`,
    {
      sslValidate: true,
      sslCA: ca,
      useNewUrlParser: true
    })
  } else {
    console.log(`connecting to Mongo at ${dbHost}`)
    connect = MongoClient.connect(`mongodb://${dbUsername}:${dbPassword}@${dbHost}:${dbPort}/${dbName}`, { useUnifiedTopology: true })
  }
  // Configure mongo and start server.
  return connect
    .then((client) => {
      const db = client.db(dbName)
      db.collection('resources').createIndex({id: 1}, {unique: true})
      db.collection('resourceVersions').createIndex({id: 1, timestamp: 1}, {unique: true})
      db.collection('resourceMetadata').createIndex({id: 1}, {unique: true})
      return db
    })
    .catch((error) => {
      throw error
    })
}
