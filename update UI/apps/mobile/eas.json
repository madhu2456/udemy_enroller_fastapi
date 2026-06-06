{
	"cli": {
		"version": ">= 15.0.15",
		"appVersionSource": "remote"
	},
	"build": {
		"development": {
			"developmentClient": true,
			"distribution": "internal",
			"env": {
				"SENTRY_DISABLE_AUTO_UPLOAD": "true"
			}
		},
		"preview": {
			"distribution": "internal",
			"env": {
				"SENTRY_DISABLE_AUTO_UPLOAD": "true"
			}
		},
		"production": {
			"autoIncrement": true,
			"android": {
				"buildType": "app-bundle"
			},
			"env": {
				"SENTRY_DISABLE_AUTO_UPLOAD": "true"
			}
		}
	},
	"submit": {
		"production": {
			"android": {
				"serviceAccountKeyPath": "./google-service-account.json",
				"track": "internal",
				"releaseStatus": "draft",
				"changesNotSentForReview": false
			}
		}
	}
}
