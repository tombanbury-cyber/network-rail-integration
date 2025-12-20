# Copilot Instructions for network-rail-integration

## Project Overview
This is a Home Assistant Custom Component (HACS) integration for tracking UK train movements using Network Rail data.  

## Code Style and Standards

### Python
- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Write docstrings for all classes and public methods
- Maintain Python 3.11+ compatibility (or adjust based on your minimum version)

### Home Assistant Specific
- Follow Home Assistant's integration development guidelines
- Use the Home Assistant coding standards and patterns
- Implement proper entity naming conventions
- Use Home Assistant's built-in logging (`_LOGGER`)
- Follow async/await patterns for I/O operations

## Architecture Guidelines

### Integration Structure
- Keep API calls separate in a dedicated client/API module
- Use coordinator pattern for data updates (`DataUpdateCoordinator`)
- Implement proper error handling for Network Rail API failures
- Cache responses appropriately to avoid rate limiting

### Configuration
- Support both UI (config flow) and YAML configuration where appropriate
- Validate user inputs thoroughly
- Store API credentials securely

### Entities
- Create appropriate entity types (sensor, binary_sensor, etc.)
- Include proper device information
- Implement unique IDs correctly
- Add appropriate entity categories and device classes

## Testing
- Write unit tests for core functionality
- Mock external API calls in tests
- Test error conditions and edge cases
- Ensure tests are isolated and repeatable

## Documentation
- Update README. md with setup instructions
- Document configuration options
- Include examples of API usage
- Add troubleshooting section for common issues

## Network Rail API
- Handle authentication properly
- Respect rate limits
- Parse STOMP/data feed messages correctly
- Handle connection drops and reconnections gracefully

## Dependencies
- Minimize external dependencies
- Prefer Home Assistant's built-in libraries
- Document any required system dependencies

## Error Handling
- Log errors with appropriate severity levels
- Provide user-friendly error messages
- Implement retry logic for transient failures
- Gracefully handle API unavailability

## Performance
- Use async I/O for all network operations
- Avoid blocking the event loop
- Implement efficient data polling intervals
- Clean up resources properly on shutdown

## Version Management

### Automatic Version Bumping
When making changes that require a version update, automatically bump the version number in `manifest.json`:

- **Patch version** (0.0.X): Bug fixes, minor changes, documentation updates
- **Minor version** (0.X.0): New features, non-breaking changes, significant improvements
- **Major version** (X.0.0): Breaking changes, major refactors, API changes

**Process:**
1. Read the current version from `custom_components/network_rail_integration/manifest.json`
2. Determine the appropriate version bump based on the change type
3. Update the `"version"` field in manifest.json using semantic versioning (semver)
4. Include the version bump in the same commit/PR as the changes
5. Update CHANGELOG.md or release notes with the new version and changes

**Example:**
- Current version: `"version": "1.2.3"`
- After bug fix: `"version": "1.2.4"`
- After new feature: `"version": "1.3.0"`
- After breaking change: `"version": "2.0.0"`

**Guidelines:**
- Always bump the version when making functional changes
- Keep the version format as a string in manifest.json: `"version": "X.Y.Z"`
- Ensure version matches any GitHub releases or HACS version tags
- Consider using GitHub Actions for automated version bumping on release
