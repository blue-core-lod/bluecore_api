import superagent from 'superagent'

if(process.argv.length !== 4 && process.argv.length !== 5) {
  console.error('Usage: bin/copy <source API url> <destination API url> [source querystring (optional)]')
  process.exit(1) // eslint-disable-line no-process-exit
}

class ResourcesCopier {
  constructor (sourceApiUrl, destApiUrl, querystring) {
    this.sourceApiUrl = sourceApiUrl
    this.destApiUrl = destApiUrl
    this.querystring = querystring
  }

  async copy () {
    let nextUrl = this.queryString ? `${this.sourceApiUrl}/resource?${this.querystring}` : `${this.sourceApiUrl}/resource`
    while(nextUrl) {
      /* eslint-disable no-await-in-loop */
      /* eslint-disable no-continue */
      console.log(`Fetching ${nextUrl}`)
      const page = await ResourcesCopier.fetchPage(nextUrl)
      for(const resource of page.data) {
        // Don't copy base templates
        if(resource.uri.includes('resource/sinopia:template')) continue;
        // Dunno, but it causes problems.
        if(resource.uri.includes('resource/null')) continue;
        await this.postResource(resource)
      }
      nextUrl = page.links.next
    }
  }

  static fetchPage (url) {
    return superagent.get(url)
      .then((response) => {
        if(!response.ok) {
          throw new Error(`Get failed with ${response.status} for ${url}`)
        }
        return response.body
      })
  }

  postResource (resource) {
    const newResource = JSON.parse(JSON.stringify(resource).replace(new RegExp(this.sourceApiUrl, 'g'), this.destApiUrl))

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

const copyResources = async () => {
  try {
    await new ResourcesCopier(process.argv[2], process.argv[3]).copy()
    console.log('Done')
  } catch(err) {
    console.error(err)
  }
}

copyResources()
