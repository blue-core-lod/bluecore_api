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

echo "Importing resource template docs"
sed s/localhost/api/g /scripts/rt_literal_property_attrs_doc.json | mongoimport --host=mongo:27017 --db=sinopia_repository --collection=resources
sed s/localhost/api/g /scripts/rt_lookup_property_attrs_doc.json | mongoimport --host=mongo:27017 --db=sinopia_repository --collection=resources
sed s/localhost/api/g /scripts/rt_property_template_doc.json | mongoimport --host=mongo:27017 --db=sinopia_repository --collection=resources
sed s/localhost/api/g /scripts/rt_resource_property_attrs_doc.json | mongoimport --host=mongo:27017 --db=sinopia_repository --collection=resources
sed s/localhost/api/g /scripts/rt_resource_template_doc.json | mongoimport --host=mongo:27017 --db=sinopia_repository --collection=resources
sed s/localhost/api/g /scripts/rt_uri_property_attrs_doc.json | mongoimport --host=mongo:27017 --db=sinopia_repository --collection=resources
sed s/localhost/api/g /scripts/rt_uri_doc.json | mongoimport --host=mongo:27017 --db=sinopia_repository --collection=resources
