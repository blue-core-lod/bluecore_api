import express from "express"

const groupsRouter = express.Router()

groupsRouter.get("/", (req, res) => {
  console.log(`Received get to ${req}`)

  // For now, hardcode the groups response: see https://github.com/ld4p/sinopia_api/issues/143
  // Later, this will be dynamically fetched from Cognito and then used by the editor
  const groups = [
    { id: "alberta", label: "University of Alberta" },
    { id: "boulder", label: "University of Colorado, Boulder" },
    { id: "chicago", label: "University of Chicago" },
    { id: "cornell", label: "Cornell University" },
    { id: "dlc", label: "Library of Congress" },
    { id: "duke", label: "Duke University" },
    { id: "frick", label: "Frick Art Reference Library" },
    { id: "harvard", label: "Harvard University" },
    { id: "hrc", label: "University of Texas, Austin, Harry Ransom Center" },
    { id: "ld4p", label: "LD4P" },
    { id: "michigan", label: "University of Michigan" },
    { id: "minnesota", label: "University of Minnesota" },
    { id: "mla", label: "Music Library Association" },
    { id: "nlm", label: "National Library of Medicine" },
    { id: "northwestern", label: "Northwestern University" },
    { id: "other", label: "Other" },
    { id: "pcc", label: "PCC" },
    { id: "penn", label: " 'University of Pennsylvania" },
    { id: "princeton", label: "Princeton University" },
    { id: "stanford", label: "Stanford University" },
    { id: "tamu", label: " 'Texas A&M University" },
    { id: "ucdavis", label: "University of California, Davis" },
    { id: "ucsd", label: "University of California, San Diego" },
    { id: "washington", label: "University of Washington" },
    { id: "yale", label: "Yale University" },
  ]
  res.json({ data: groups })
})

export default groupsRouter
