import { ttlFromJsonld } from '../src/rdf.js'
const resource = require('./__fixtures__/resource_6852a770-2961-4836-a833-0b21a9b68041.json')

const resourceTtl = `<https://api.development.sinopia.io/resource/6852a770-2961-4836-a833-0b21a9b68041> a <http://id.loc.gov/ontologies/bibframe/AbbreviatedTitle>;
    <http://id!loc!gov/ontologies/bibframe/mainTitle> "foo"@eng;
    <http://sinopia!io/vocabulary/hasResourceTemplate> "profile:bf2:Title:AbbrTitle".
`
describe('ttlFromJsonld', () => {
  it('returns the resource RDF in turtle format', async () => {
    expect(await ttlFromJsonld(resource.data)).toEqual(resourceTtl)
  })

  it('returns a blank serialization if not provided JSONld', async () => {
    expect(await ttlFromJsonld(resource)).toEqual('')
  })
})
