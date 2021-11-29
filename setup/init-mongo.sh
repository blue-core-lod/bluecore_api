#!/bin/bash
echo "sleeping for 5 seconds while mongo starts"
sleep 5

echo "Initiating replica set"
mongo --host mongo:27017 <<EOF
  // Initiate replica set
  rs.initiate();
EOF

echo "Initializing db"
mongo --host mongo:27017 <<EOF
  // See https://docs.mongodb.com/manual/reference/method/
  use sinopia_repository

  db.createUser(
    {
      user: "sinopia",
      pwd: "sekret",
      roles: [
        {
          role: "readWrite",
          db: "sinopia_repository"
        }
      ]
    }
  )

  db.resources.createIndex({id: 1}, {unique: true})
  db.resources.createIndex({types: 1})
  db.resources.createIndex({group: 1})
  db.resources.createIndex({editGroups: 1})
  db.resources.createIndex({templateId: 1})
  db.resources.createIndex({bfAdminMetadataRefs: 1})
  db.resources.createIndex({bfItemRefs: 1})
  db.resources.createIndex({bfInstanceRefs: 1})
  db.resources.createIndex({bfWorkRefs: 1})
  db.resourceVersions.createIndex({id: 1, timestamp: 1}, {unique: true})
  db.resourceMetadata.createIndex({id: 1}, {unique: true})
  db.users.createIndex({id: 1}, {unique: true})
EOF
