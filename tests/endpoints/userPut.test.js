import connect from "mongo.js"
import request from "supertest"
import app from "app.js"

jest.mock("mongo.js")
jest.mock("jwt.js", () => {
  return {
    __esModule: true,
    default: jest
      .fn()
      .mockReturnValue({ secret: "shhhhhhared-secret", algorithms: ["HS256"] }),
  }
})

describe("PUT /user/:userId/history/:historyType/:historyItemId", () => {
  it("inserts new history item", async () => {
    const user = {
      _id: "abc123",
      id: "abc123",
      data: {
        history: {
          template: [],
          resource: [],
          search: [{ id: "def456", payload: "query=propaganda" }],
        },
      },
    }

    const mockUserUpdate = jest.fn().mockResolvedValue({ nModified: 1 })
    const mockFindOne = jest.fn().mockResolvedValue(user)
    const mockCollection = (collectionName) => {
      return {
        users: { update: mockUserUpdate, findOne: mockFindOne },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .put("/user/nchomsky/history/search/ghi789")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg"
      )
      .send({ payload: "query=disinformation" })
    expect(res.statusCode).toEqual(200)
    const resBody = {
      id: "abc123",
      data: {
        history: {
          template: [],
          resource: [],
          search: [
            { id: "ghi789", payload: "query=disinformation" },
            { id: "def456", payload: "query=propaganda" },
          ],
        },
      },
    }
    expect(res.body).toEqual(resBody)
    const saveUser = { ...resBody, _id: "abc123" }

    expect(mockUserUpdate).toHaveBeenCalledWith({ id: "nchomsky" }, saveUser, {
      replaceOne: true,
    })
  })
  it("does not add duplicates", async () => {
    const user = {
      _id: "abc123",
      id: "abc123",
      data: {
        history: {
          template: [],
          resource: [],
          search: [
            { id: "def456", payload: "query=propaganda" },
            { id: "ghi789", payload: "query=disinformation" },
          ],
        },
      },
    }

    const mockUserUpdate = jest.fn().mockResolvedValue({ nModified: 1 })
    const mockFindOne = jest.fn().mockResolvedValue(user)
    const mockCollection = (collectionName) => {
      return {
        users: { update: mockUserUpdate, findOne: mockFindOne },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .put("/user/nchomsky/history/search/ghi789")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg"
      )
      .send({ payload: "query=disinformation" })
    expect(res.statusCode).toEqual(200)
    const resBody = {
      id: "abc123",
      data: {
        history: {
          template: [],
          resource: [],
          search: [
            { id: "ghi789", payload: "query=disinformation" },
            { id: "def456", payload: "query=propaganda" },
          ],
        },
      },
    }
    expect(res.body).toEqual(resBody)
  })
  it("limits the number of items", async () => {
    const user = {
      _id: "abc123",
      id: "abc123",
      data: {
        history: {
          template: [],
          resource: [],
          search: [
            { id: "1", payload: "query=1" },
            { id: "2", payload: "query=2" },
            { id: "3", payload: "query=3" },
            { id: "4", payload: "query=4" },
            { id: "5", payload: "query=5" },
            { id: "6", payload: "query=6" },
            { id: "7", payload: "query=7" },
            { id: "8", payload: "query=8" },
            { id: "9", payload: "query=9" },
            { id: "10", payload: "query=10" },
          ],
        },
      },
    }

    const mockUserUpdate = jest.fn().mockResolvedValue({ nModified: 1 })
    const mockFindOne = jest.fn().mockResolvedValue(user)
    const mockCollection = (collectionName) => {
      return {
        users: { update: mockUserUpdate, findOne: mockFindOne },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .put("/user/nchomsky/history/search/ghi789")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg"
      )
      .send({ payload: "query=disinformation" })
    expect(res.statusCode).toEqual(200)
    const resBody = {
      id: "abc123",
      data: {
        history: {
          template: [],
          resource: [],
          search: [
            { id: "ghi789", payload: "query=disinformation" },
            { id: "1", payload: "query=1" },
            { id: "2", payload: "query=2" },
            { id: "3", payload: "query=3" },
            { id: "4", payload: "query=4" },
            { id: "5", payload: "query=5" },
            { id: "6", payload: "query=6" },
            { id: "7", payload: "query=7" },
            { id: "8", payload: "query=8" },
            { id: "9", payload: "query=9" },
          ],
        },
      },
    }
    expect(res.body).toEqual(resBody)
  })

  it("requires auth", async () => {
    const res = await request(app)
      .put("/user/nchomsky/history/search/ghi789")
      .send({ payload: "query=disinformation" })
    expect(res.statusCode).toEqual(401)
  })
})
