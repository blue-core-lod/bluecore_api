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

describe("POST /user/:userId", () => {
  const mockUserInsert = jest.fn().mockResolvedValue()
  const mockCollection = (collectionName) => {
    return {
      users: { insert: mockUserInsert },
    }[collectionName]
  }
  const mockDb = { collection: mockCollection }
  connect.mockImplementation(mockConnect(mockDb))

  it("creates a new user", async () => {
    const res = await request(app)
      .post("/user/nchomsky")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg"
      )
      .send()
    expect(res.statusCode).toEqual(201)
    const resBody = {
      id: "nchomsky",
      data: {
        history: {
          template: [],
          resource: [],
          search: [],
        },
      },
    }
    expect(res.body).toEqual(resBody)
    expect(res.header.location).toEqual(
      "https://api.development.sinopia.io/user/nchomsky"
    )
    expect(mockUserInsert).toHaveBeenCalledWith(resBody)
  })

  it("requires auth", async () => {
    const res = await request(app).post("/user/nchomsky").send()
    expect(res.statusCode).toEqual(401)
  })
  it("returns 409 if user is not unique", async () => {
    const err = new Error("Ooops")
    err.code = 11000
    mockUserInsert.mockRejectedValue(err)
    const res = await request(app)
      .post("/user/nchomsky")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg"
      )
      .send()
    expect(res.statusCode).toEqual(409)
    expect(res.body).toEqual([
      {
        title: "Conflict",
        details: "ID is already in use. Please choose a unique ID.",
        status: "409",
      },
    ])
  })
})
