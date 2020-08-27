import connect from 'mongo.js'
import request from 'supertest'
import app from 'app.js'
const resource = require('../__fixtures__/resource_6852a770-2961-4836-a833-0b21a9b68041.json')
const resBody = require('../__fixtures__/resp_6852a770-2961-4836-a833-0b21a9b68041.json')

// To avoid race conditions with mocking connect, testing of resources is split into
// Multiple files.

jest.mock('mongo.js')

describe('GET /repository/:resourceId', () => {
  const mockFindOne = jest.fn().mockResolvedValue(resource)
  const mockCollection = (collectionName) => {
    return {
      resources: {findOne: mockFindOne}
    }[collectionName]
  }
  const mockDb = {collection: mockCollection}
  connect.mockReturnValue(mockDb)

  it('returns the resource', async () => {
    const res = await request(app)
      .get('/repository/6852a770-2961-4836-a833-0b21a9b68041')
      .set('Accept', 'application/json')
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual(resBody)
    expect(mockFindOne).toHaveBeenCalledWith({id: '6852a770-2961-4836-a833-0b21a9b68041'})
  })
})
