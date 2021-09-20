import request from "supertest"
import app from "app.js"
import * as aws from "aws.js"

jest.mock("aws.js")

describe("GET /groups", () => {
  const groups = [
    { id: "stanford", label: "Stanford University" },
    { id: "cornell", label: "Cornell University" },
  ]

  aws.listGroups.mockResolvedValue(groups)

  it("returns the groups", async () => {
    const res = await request(app)
      .get("/groups")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body.data).toEqual(expect.arrayContaining(groups))
  })
})
