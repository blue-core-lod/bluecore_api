import connect from "mongo.js"
import request from "supertest"
import app from "app.js"

jest.mock("mongo.js")

const mockResponse = jest.fn().mockResolvedValue(1)
const response = { count: 1 }
const templateOnlyQuery = {
  types: "http://sinopia.io/vocabulary/ResourceTemplate",
}
const resourceOnlyQuery = {
  types: {
    $not: { $eq: "http://sinopia.io/vocabulary/ResourceTemplate" },
  },
}

describe("GET /metrics/userCount", () => {
  it("returns the total user count", async () => {
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

describe("GET /metrics/resourceCount", () => {
  it("returns the total resource count when user asks for 'all'", async () => {
    const mockCollection = (collectionName) => {
      return {
        resources: { count: mockResponse },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get("/metrics/resourceCount/all")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual(response)
    expect(mockResponse).toHaveBeenCalledWith(null)
  })

  it("returns the just the resource templates resource count when user asks for 'template'", async () => {
    const mockCollection = (collectionName) => {
      return {
        resources: { count: mockResponse },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get("/metrics/resourceCount/template")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual(response)
    expect(mockResponse).toHaveBeenCalledWith(templateOnlyQuery)
  })

  it("returns the just the resources count when user asks for 'resource'", async () => {
    const mockCollection = (collectionName) => {
      return {
        resources: { count: mockResponse },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get("/metrics/resourceCount/resource")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual(response)
    expect(mockResponse).toHaveBeenCalledWith(resourceOnlyQuery)
  })
})