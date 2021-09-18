import Writer from "n3/lib/N3Writer.js"
import rdf from "rdf-ext"
import { Readable } from "stream"
import { JsonLdParser } from "jsonld-streaming-parser"
import createError from "http-errors"

export const datasetFromJsonld = (jsonld) => {
  const parserJsonld = new JsonLdParser()

  const input = new Readable({
    read: () => {
      input.push(JSON.stringify(jsonld))
      input.push(null)
    },
  })

  const output = parserJsonld.import(input)
  const dataset = rdf.dataset()

  output.on("data", (quad) => {
    dataset.add(quad)
  })

  return new Promise((resolve, reject) => {
    output.on("end", resolve)
    output.on("error", (err) => reject(err))
  }).then(() => dataset)
}

export const n3FromJsonld = (jsonld, asTurtle) => {
  return datasetFromJsonld(jsonld).then((dataset) => {
    const opts = asTurtle ? { format: "Turtle" } : { format: "N-Triples" }
    const writer = new Writer(opts)
    writer.addQuads(dataset.toArray())
    return new Promise((resolve, reject) => {
      writer.end((error, results) => {
        if (error) reject(error)
        resolve(results)
      })
    })
  })
}

export const ttlFromJsonld = (jsonld) => {
  return n3FromJsonld(jsonld, true)
}

export const checkJsonld = async (req, resp, next) => {
  const dataFromReqBody = req.body.data

  if (dataFromReqBody === null) return next(new createError.BadRequest())
  if (dataFromReqBody.length === 0)
    return next(new createError.BadRequest("Data array must not be empty."))
  dataFromReqBody.forEach((obj) => {
    if (Object.keys(obj).length === 0)
      return next(
        new createError.BadRequest("Data array must not have empty objects.")
      )
  })

  try {
    await datasetFromJsonld(dataFromReqBody)
  } catch (err) {
    return next(
      new createError.BadRequest(`Unparseable jsonld: ${err.message}`)
    )
  }
  next()
}
