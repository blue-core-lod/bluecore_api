/* eslint multiline-comment-style: ["error", "starred-block"] */
/*
 * Note: This test and docdb.test.js are nearly identical,
 * however the 2 main differences do not properly reset (ENV)
 * when run in the same test suite. Seperating them is required.
 */
import monk from 'monk'

jest.mock('monk')

describe('connect to mongodb', () => {
  it('returns a mongo client', () => {
    process.env.MONGODB_IS_AWS = 'false'
    const connect = require('mongo.js').default // eslint-disable-line global-require
    connect()
    expect(monk).toHaveBeenCalledWith("mongodb://sinopia:sekret@localhost:27017/sinopia_repository", {"useUnifiedTopology": true})
  })
})
