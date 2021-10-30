#!/bin/bash
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
EOF
