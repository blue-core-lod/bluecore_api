import request from "supertest"
import app from "app.js"

describe("GET /metrics/userCount", () => {
  it("returns the total user count", async () => {
    const res = await request(app)
      .get("/metrics/userCount")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual({ count: 1 })
  })
})
