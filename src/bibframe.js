export const isBfInstance = (resource) => {
  return resource.types.includes(
    "http://id.loc.gov/ontologies/bibframe/Instance"
  )
}

export const isBfWork = (resource) => {
  return resource.types.includes("http://id.loc.gov/ontologies/bibframe/Work")
}

export const isBfItem = (resource) => {
  return resource.types.includes("http://id.loc.gov/ontologies/bibframe/Item")
}

export const isBfAdminMetadata = (resource) => {
  return resource.types.includes(
    "http://id.loc.gov/ontologies/bibframe/AdminMetadata"
  )
}
