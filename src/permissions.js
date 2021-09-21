import createError from "http-errors"
import _ from "lodash"

export const canCreate = (req, resp, next) => {
  // The user must be a member of the owning group (as provided in the resource being POSTed)
  if (isNoAuth()) return next()
  const userGroups = getGroups(req)
  const resourceGroup = req.body.group
  if (!userGroups.includes(resourceGroup))
    return next(
      new createError.Unauthorized("User must a member of the resource's group")
    )
  next()
}

export const canEdit = (req, resp, next) => {
  if (isNoAuth()) return next()
  // If group or editGroups has changed (as determined by comparing against the last resource version), the user must be a member of the owning group.
  // Otherwise, the user must be a member of the owning group or one of the editing groups
  const userGroups = getGroups(req)
  const resourceGroup = req.body.group
  const resourceEditGroups = req.body.editGroups
  req.db
    .collection("resourceMetadata")
    .findOne(
      { id: req.params.resourceId },
      { projection: { versions: { $slice: -1 } } }
    )
    .then((result) => {
      if (!result) return next(new createError.NotFound())
      const lastResourceGroup = result.versions[0].group
      const lastResourceEditGroups = result.versions[0].editGroups
      // If group or edit group changed, must be owner.
      if (
        (resourceGroup !== lastResourceGroup ||
          !_.isEqual(resourceEditGroups, lastResourceEditGroups)) &&
        !userGroups.includes(lastResourceGroup)
      )
        return next(
          new createError.Unauthorized(
            "User must a member of the resource's group"
          )
        )
      // If group changed, must be member of new group.
      if (
        resourceGroup !== lastResourceGroup &&
        !userGroups.includes(resourceGroup)
      )
        return next(
          new createError.Unauthorized("User must a member of the new group")
        )
      // Must be owner or member of edit group to edit.
      if (
        !(
          userGroups.includes(lastResourceGroup) ||
          _.intersection(userGroups, lastResourceEditGroups).length
        )
      )
        return next(
          new createError.Unauthorized(
            "User must a member of the resource's group or editGroups"
          )
        )
      next()
    })
    .catch(next)
}

export const canDelete = (req, resp, next) => {
  if (isNoAuth()) return next()
  // The user must be a member of the owning group
  const userGroups = getGroups(req)
  req.db
    .collection("resources")
    .findOne({ id: req.params.resourceId }, { projection: { group: 1 } })
    .then((result) => {
      if (!result) return next(new createError.NotFound())
      if (!userGroups.includes(result.group))
        return next(
          new createError.Unauthorized(
            "User must a member of the resource's group"
          )
        )
      next()
    })
    .catch(next)
}

const getGroups = (req) => req.user["cognito:groups"] || []

const isNoAuth = () => process.env.NO_AUTH === "true"
