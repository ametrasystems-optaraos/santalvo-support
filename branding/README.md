# Santalvo Support

Santalvo Support is the remote-support app of Santalvo Systems. It is RustDesk 1.5.3
(https://github.com/rustdesk/rustdesk) with our name and logo. It connects only to our own
support server.

## License

Licensed under the GNU Affero General Public License v3.0 (see `LICENCE`), the same license
as RustDesk. RustDesk is copyright Purslane Tech Pte. Ltd. and its contributors. "RustDesk" is
their trademark. This build is not made or endorsed by them.

## How this repository is made

1. Start from an untouched RustDesk release tag. `libs/hbb_common` is included as a plain folder.
2. Run `python3 branding/apply_branding.py`. It changes the app name, the icons and the
   Windows, macOS, Linux and Android package names.
3. Run `python3 branding/trim_workflow.py`. It cuts the CI down to the platforms we ship.

The source contains no server address and no key, only the placeholders
`@@RENDEZVOUS_SERVER@@` and `@@RS_PUB_KEY@@`. Each build fills them in from repository secrets.
Builds are encrypted before they are stored and are never published publicly.
