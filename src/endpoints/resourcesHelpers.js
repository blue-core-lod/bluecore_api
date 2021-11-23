import _ from "lodash"
import createError from "http-errors"
import {
  isBfWork,
  isBfInstance,
  isBfItem,
  isBfAdminMetadata,
  isSinopiaAdminMetadata,
} from "../bibframe.js"

const apiBaseUrl = process.env.API_BASE_URL

export const resourceUriFor = (req) => {
  return `${baseUrlFor(req)}/${req.params.resourceId}`
}

const baseUrlFor = (req) => {
  if (apiBaseUrl) return `${apiBaseUrl}/resource`
  return `${req.protocol}://${req.hostname}:${req.port}/resource`
}

export const pageUrlFor = (req, limit, start, qs) => {
  const params = { limit, start }
  Object.keys(qs).forEach((key) => {
    if (["group", "updatedAfter", "updatedBefore", "type"].includes(key)) {
      params[key] = qs[key]
    }
  })
  const queryString = Object.entries(params)
    .map(([key, value]) => [key, encodeURIComponent(value)].join("="))
    .join("&")
  return `${baseUrlFor(req)}?${queryString}`
}

export const queryFor = (qs) => {
  const query = {}
  if (qs.group) query.group = qs.group
  if (qs.type) query.types = qs.type
  if (qs.updatedAfter || qs.updatedBefore) query.timestamp = {}
  if (qs.updatedAfter) query.timestamp.$gte = parseDate(qs.updatedAfter)
  if (qs.updatedBefore) query.timestamp.$lte = parseDate(qs.updatedBefore)
  return query
}

export const parseDate = (dateString) => {
  const date = new Date(dateString)
  if (isNaN(date))
    throw new createError.BadRequest(`Invalid date-time: ${dateString}`)

  return date
}

export const forReturn = (item) => {
  // Map ! back to . in key names
  const newItem = replaceInKeys(item, "!", ".")
  delete newItem._id
  return newItem
}

export const mergeRefs = (resource, refResources) => {
  resource.bfAdminMetadataInferredRefs = []
  resource.bfItemInferredRefs = []
  resource.bfInstanceInferredRefs = []
  resource.bfWorkInferredRefs = []
  resource.sinopiaHasLocalAdminMetadataInferredRefs = []
  refResources.forEach((refResource) =>
    addRefsToResource(resource, refResource)
  )
  resource.bfAdminMetadataAllRefs = _.uniq([
    ...(resource.bfAdminMetadataRefs ?? []),
    ...(resource.bfAdminMetadataInferredRefs ?? []),
  ])
  resource.bfItemAllRefs = _.uniq([
    ...(resource.bfItemRefs ?? []),
    ...(resource.bfItemInferredRefs ?? []),
  ])
  resource.bfInstanceAllRefs = _.uniq([
    ...(resource.bfInstanceRefs ?? []),
    ...(resource.bfInstanceInferredRefs ?? []),
  ])
  resource.bfWorkAllRefs = _.uniq([
    ...(resource.bfWorkRefs ?? []),
    ...(resource.bfWorkInferredRefs ?? []),
  ])
  return resource
}

const addRefsToResource = (resource, refResource) => {
  if (isBfWork(refResource)) resource.bfWorkInferredRefs.push(refResource.uri)
  if (isBfInstance(refResource))
    resource.bfInstanceInferredRefs.push(refResource.uri)
  if (isBfItem(refResource)) resource.bfItemInferredRefs.push(refResource.uri)
  if (isBfAdminMetadata(refResource))
    resource.bfAdminMetadataInferredRefs.push(refResource.uri)
  if (isSinopiaAdminMetadata(refResource))
    resource.sinopiaHasLocalAdminMetadataInferredRefs.push(refResource.uri)
}

export const resourceForSave = (resource, id, uri, timestamp) => {
  // Map . to ! in key names because Mongo doesn't like . in key names. Sigh.
  const newResource = replaceInKeys(resource, ".", "!")

  newResource.id = id
  // If resource has a uri, keep it. This is to support migrations.
  if (!newResource.uri) newResource.uri = uri
  newResource.timestamp = timestamp
  return newResource
}

export const versionEntry = (resource) => ({
  timestamp: resource.timestamp,
  user: resource.user,
  group: resource.group,
  editGroups: resource.editGroups,
  templateId: resource.templateId,
})

const replaceInKeys = (obj, from, to) => {
  return _.cloneDeepWith(obj, function (cloneObj) {
    if (!_.isPlainObject(cloneObj)) return
    const newObj = {}
    _.keys(cloneObj).forEach((key) => {
      const newKey = key.replace(new RegExp(`\\${from}`, "g"), to)
      newObj[newKey] = replaceInKeys(cloneObj[key], from, to)
    })
    return newObj
  })
}
