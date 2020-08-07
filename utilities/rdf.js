// import { Writer as N3Writer } from 'n3'
import N3 from 'n3';
// import N3Parser from 'n3/lib/N3Parser'
import rdf from 'rdf-ext'
// import _ from 'lodash'
// import Config from 'Config'
// import CryptoJS from 'crypto-js'
// import SerializerJsonld from '@rdfjs/serializer-jsonld'
// const concatStream = require('concat-stream')
import { Readable } from 'stream'
import ParserJsonld  from '@rdfjs/parser-jsonld'

export const datasetFromJsonld = (jsonld) => {
  const parserJsonld = new ParserJsonld()

  const input = new Readable({
    read: () => {
      input.push(JSON.stringify(jsonld))
      input.push(null)
    }
  })

  const output = parserJsonld.import(input)
  const dataset = rdf.dataset()

  output.on('data', quad => {
    dataset.add(quad)
  })

  return new Promise((resolve, reject) => {
    output.on('end', resolve)
    output.on('error', reject)
  })
    .then(() => {
      return dataset
    })
}

export const n3FromJsonld = (jsonld, asTurtle) => {
  return datasetFromJsonld(jsonld)
    .then((dataset) => {
      const opts = !asTurtle ? {format: 'N-Triples'} : {format: 'Turtle'}
      const writer = new N3.Writer(opts)
      writer.addQuads(dataset.toArray())
      return new Promise((resolve, reject) => {
        writer.end((error, results) => {
          if(error) reject(error)
          resolve(results)
        })
      })
    })
}

export const ttlFromJsonld = (jsonld) => {
  return n3FromJsonld(jsonld, true)
}
