import connect from "mongo.js"
import request from "supertest"
import app from "app.js"

const user = {
  _id: "abc123",
  id: "nchomsky",
  data: {
    history: {
      template: [],
      resource: [],
      search: [],
    },
  },
}

jest.mock("mongo.js")

// GET a single user
describe("GET /user/:userId", () => {
  it("returns the user", async () => {
    const mockFindOne = jest.fn().mockResolvedValue(user)
    const mockCollection = (collectionName) => {
      return {
        users: { findOne: mockFindOne },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get("/user/nchomsky")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    const resBody = { ...user }
    delete resBody._id
    expect(res.body).toEqual(resBody)
    expect(mockFindOne).toHaveBeenCalledWith({ id: "nchomsky" })
  })
})
