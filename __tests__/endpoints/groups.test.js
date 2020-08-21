import connect from 'mongo.js'
import request from 'supertest'
import app from 'app.js'

jest.mock('mongo.js')

describe('GET /groups', () => {
  const mockDistinct = jest.fn().mockResolvedValue([
'stanford',
'pcc'
])
  const mockCollection = jest.fn().mockReturnValue({distinct: mockDistinct})
  const mockDb = {collection: mockCollection}
  connect.mockReturnValue(mockDb)

  it('returns the resource', async () => {

    const res = await request(app)
      .get('/groups')
      .set('Accept', 'application/json')
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual({data: [
{id: 'stanford'},
{id: 'pcc'}
]})
    expect(mockDistinct.mock.calls[0][0]).toBe('group')
  })
})
