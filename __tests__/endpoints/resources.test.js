import connect from 'mongo.js'
import request from 'supertest'
import app from 'app.js'
const resource = require('../__fixtures__/resource_6852a770-2961-4836-a833-0b21a9b68041.json')
const resBody = require('../__fixtures__/resp_6852a770-2961-4836-a833-0b21a9b68041.json')

jest.mock('mongo.js')

describe('GET /repository/:resourceId', () => {
  const mockFindOne = jest.fn().mockResolvedValue(resource)
  const mockCollection = jest.fn().mockReturnValue({findOne: mockFindOne})
  const mockDb = {collection: mockCollection}
  connect.mockReturnValue(mockDb)

  it('returns the resource', async () => {

    const res = await request(app)
      .get('/repository/1fd7a005-1273-4def-823d-876f900d8caa')
      .set('Accept', 'application/json')
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual(resBody)
  })
})
