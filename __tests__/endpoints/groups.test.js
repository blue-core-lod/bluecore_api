import request from "supertest"
import app from "app.js"

describe("GET /groups", () => {
  it("returns the resource", async () => {
    const res = await request(app)
      .get("/groups")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body.data).toEqual(
      expect.arrayContaining([
        { id: "stanford", label: "Stanford University" },
        { id: "cornell", label: "Cornell University" },
      ])
    )
    expect(res.body.data.length).toBeGreaterThanOrEqual(25)
  })
})
