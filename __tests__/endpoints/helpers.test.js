import request from "supertest"
import app from "app.js"
import * as aws from "aws.js"

jest.mock("aws.js")
jest.mock("jwt.js", () => {
  return {
    __esModule: true,
    default: jest
      .fn()
      .mockReturnValue({ secret: "shhhhhhared-secret", algorithms: ["HS256"] }),
  }
})

describe("POST /helpers/langDetection", () => {
  const langs = [
    { language: "en", score: 0.4512737989425659 },
    { language: "es", score: 0.23285673558712006 },
  ]

  aws.detectLanguage.mockResolvedValue(langs)

  it("returns the languages", async () => {
    const res = await request(app)
      .post("/helpers/langDetection")
      .set("Accept", "application/json")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMiwiY29nbml0bzp1c2VybmFtZSI6Impkb2UifQ.Rmfs_TH1hYeCcQrTmoOXxA3f0UC1yhgTRdYLUSmRw-c"
      )
      .set("Content-Type", "text/plain")
      .send("el diablo")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual({
      query: "el diablo",
      data: langs,
    })
  })
})
