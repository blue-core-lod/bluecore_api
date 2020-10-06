/* eslint multiline-comment-style: ["error", "starred-block"] */
/*
 * Note: This test and mongodb.test.js are nearly identical,
 * however the 2 main differences do not properly reset (ENV)
 * when run in the same test suite. Seperating them is required.
 */
import fs from 'fs'
import monk from 'monk'

jest.mock('monk')

describe('connect to aws docdb', () => {
  it('returns an aws client', () => {
    process.env.MONGODB_IS_AWS = 'true'
    const connect = require('mongo.js').default // eslint-disable-line global-require
    const ca = [fs.readFileSync('rds-combined-ca-bundle.pem')]
    connect()
    expect(monk).toHaveBeenCalledWith("mongodb://sinopia:sekret@localhost:27017/sinopia_repository?ssl=true&replicaSet=rs0&readPreference=secondaryPreferred&retryWrites=false", { sslValidate: true, sslCA: ca, useNewUrlParser: true })
  })
})
