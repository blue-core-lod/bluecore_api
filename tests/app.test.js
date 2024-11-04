import request from "supertest"
import app from "app.js"

jest.mock("mongo.js")

describe("GET /", () => {
  it("returns health check", async () => {
    const res = await request(app).get("/")
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual({ all: "good" })
  })
})

describe("Openapi request validation", () => {
  it("returns bad request", async () => {
    const res = await request(app)
      .get("/resource?foo=bar")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(400)
    expect(res.body).toEqual([
      {
        details: "Unknown query parameter 'foo' at .query.foo",
        status: "400",
        title: "Bad Request",
      },
    ])
  })
})

describe("JWT validation", () => {
  it("returns unauthorized", async () => {
    const res = await request(app)
      .post("/user/nchomsky")
      .set("Authorization", "Bearer abc123")
      .send()
    expect(res.statusCode).toEqual(401)
    expect(res.body).toEqual([
      { details: "jwt malformed", status: "401", title: "Unauthorized" },
    ])
  })
})
