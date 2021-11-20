import connect from "mongo.js"
import request from "supertest"
import app from "app.js"

jest.mock("mongo.js")

const response = { count: 1 }

describe("GET /metrics/userCount", () => {
  it("returns the total user count", async () => {
    const mockResponse = jest.fn().mockResolvedValue(response)
    const mockCollection = (collectionName) => {
      return {
        users: { count: mockResponse },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get("/metrics/userCount")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual(response)
  })
})
