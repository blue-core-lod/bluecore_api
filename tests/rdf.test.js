import { checkJsonld } from "../src/rdf.js"

// This test does not work because of some Babel/Jest problem. Leaving the test here in case anyone can determine the problem.

// Const resource = require("./__fixtures__/resource_6852a770-2961-4836-a833-0b21a9b68041.json")

// Const resourceTtl = `<https://api.development.sinopia.io/resource/6852a770-2961-4836-a833-0b21a9b68041> <http://id!loc!gov/ontologies/bibframe/mainTitle> "foo"@eng;
//     <http://sinopia!io/vocabulary/hasResourceTemplate> "profile:bf2:Title:AbbrTitle";
//     A <http://id.loc.gov/ontologies/bibframe/AbbreviatedTitle>.
// `
// Describe("ttlFromJsonld", () => {
//   It("returns the resource RDF in turtle format", async () => {
//     Expect(await ttlFromJsonld(resource.data)).toEqual(resourceTtl)
//   })

//   It("returns a blank serialization if not provided JSONld", async () => {
//     Expect(await ttlFromJsonld(resource)).toEqual("")
//   })
// })

describe("checkJsonld", () => {
  const mockNext = jest.fn()

  it("returns Bad Request Error if resource is unparseable jsonld", async () => {
    const mockReq = { body: { data: [{ "@context": "object" }] } }
    await checkJsonld(mockReq, null, mockNext)
    expect(mockNext).toHaveBeenCalled()
    expect(mockNext.mock.calls[0][0].toString()).toEqual(
      "BadRequestError: Unparseable jsonld: Invalid context IRI: object"
    )
  })

  it("returns Bad Request Error if jsonld object in data array is empty", async () => {
    const mockReq = { body: { data: [{}] } }
    await checkJsonld(mockReq, null, mockNext)
    expect(mockNext).toHaveBeenCalled()
    expect(mockNext.mock.calls[0][0].toString()).toEqual(
      "BadRequestError: Data array must not have empty objects."
    )
  })

  it("returns Bad Request Error if jsonld data array is empty", async () => {
    const mockReq = { body: { data: [] } }
    await checkJsonld(mockReq, null, mockNext)
    expect(mockNext).toHaveBeenCalled()
    expect(mockNext.mock.calls[0][0].toString()).toEqual(
      "BadRequestError: Data array must not be empty."
    )
  })
})
