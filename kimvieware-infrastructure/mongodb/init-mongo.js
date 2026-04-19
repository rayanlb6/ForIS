// Initialize MongoDB database and collections for KIMVIEware
db = db.getSiblingDB('kimvieware');

// Create collections
db.createCollection('jobs');
db.createCollection('trajectories');
db.createCollection('results');

// Create indexes for jobs
db.jobs.createIndex({ "job_id": 1 }, { unique: true });
db.jobs.createIndex({ "created_at": 1 });
db.jobs.createIndex({ "status": 1 });

// Create indexes for trajectories
db.trajectories.createIndex({ "job_id": 1 });
db.trajectories.createIndex({ "phase": 1 });

// Create indexes for results
db.results.createIndex({ "job_id": 1 }, { unique: true });
db.results.createIndex({ "timestamp": 1 });

print("✅ KIMVIEware MongoDB initialized successfully");
