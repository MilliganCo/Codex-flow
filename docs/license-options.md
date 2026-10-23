# License options — decision pending

**No project license has been selected.** The private repository is being prepared for owner review. This document compares practical license features; it does not choose a license, assert ownership of unreviewed material or provide a legal conclusion.

| Option | Technical distribution implications to review |
|---|---|
| [MIT](https://opensource.org/license/mit) | Short permissive terms; retain copyright/permission notice; includes warranty/liability disclaimer |
| [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | Permissive terms with explicit patent provisions and redistribution/notice requirements |
| [BSD-3-Clause](https://opensource.org/license/BSD-3-clause) | Permissive source/binary redistribution with notice requirements and a non-endorsement clause |
| Continue private distribution | Keep access restricted while the owner decides permitted use, redistribution and contributions |

The primary texts linked above control the details. These summaries are not substitutes for reviewing the complete terms in the intended distribution context.

Before selecting any license, inventory original files, copied/modified third-party material, optional binaries, dependency metadata, contributor permissions and trademark references. The runtime uses the standard library and references external CLI/services; this does not automatically resolve rights in every existing file.

The Mercury adapter is explicitly external and **not redistributed**. No license is inferred from its local availability. Do not copy it into a release or repository merely because a bridge can import it. Upstream Harness² and Codex CLI are separately maintained projects; inspect their actual licenses and notices if any source or binaries are later bundled.

Record the owner's decision in a dedicated reviewed change that adds the selected license text and correct ownership/notice details. Do not add a generic LICENSE as part of an unrelated feature or treat private visibility as an open-source license.
