import superagent from 'superagent'

if(process.argv.length !== 4) {
  console.error('Usage: bin/copySingle <source resource url> <destination API url>')
  process.exit(1) // eslint-disable-line no-process-exit
}

class ResourceCopier {
  constructor (sourceResourceUrl, destApiUrl) {
    this.sourceResourceUrl = sourceResourceUrl
    this.sourceApiUrl = this.sourceResourceUrl.slice(0, this.sourceResourceUrl.indexOf('/resource'))
    this.destApiUrl = destApiUrl
  }

  async copy () {
    console.log(`Fetching ${this.sourceResourceUrl}`)
    const resource = await ResourceCopier.fetchResource(this.sourceResourceUrl)
    await this.postResource(resource)
  }

  static fetchResource (url) {
    return superagent.get(url)
      .then((response) => {
        if(!response.ok) {
          throw new Error(`Get failed with ${response.status} for ${url}`)
        }
        return response.text
      })
  }

  postResource (resource) {
    const newResource = JSON.parse(resource.replace(new RegExp(this.sourceApiUrl, 'g'), this.destApiUrl))
    return superagent
      .post(encodeURI(newResource.uri))
      .send(newResource)
      .set('accept', 'json')
      .then((response) => {
        if(!response.ok) {
          throw new Error(`Post failed with ${response.status} for ${newResource.uri}`)
        }
        console.log(`Posted resource to ${newResource.uri}`)
      })
  }

}

const copyResource = async () => {
  try {
    await new ResourceCopier(process.argv[2], process.argv[3]).copy()
    console.log('Done')
  } catch(err) {
    console.error(err)
  }
}

copyResource()
