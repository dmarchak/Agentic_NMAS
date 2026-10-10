# Edit a template

A configuration template is a file in the network's library, `templates/<platform>/<name>.j2` in its repository, through which a device's intent is rendered into its configuration. On Templates, **Edit…** on a template's row opens it in an editor in place, below the table. Nothing is sent to any device by editing; a deploy does that, and only through an approved template.

![Editing a template: the editor opens the template committed at HEAD and the blob it was read from; as you type it is checked, your edit rendered for every device it governs against that device's committed golden in a copy of the library outside the repository; you commit with a reason, refused naming both versions if the template moved since you opened it; the commit revokes every approval over it. No device is contacted.](diagrams/edit-template.svg)

## The steps

1. `open`: the template committed at HEAD is read from git, with the blob it came from. Read: the template as committed, its last commit, the devices it governs (bound to it, or, for a shared file such as `_common.j2`, bound to any template that imports it), and the approvals a commit would revoke. Sent: nothing. Recorded: nothing. The editor shows exactly the committed text.
2. `check`: your edit is checked as you type. Read: the network's library, copied with your edit into a folder outside the repository and removed after, and each governed device's committed golden (its golden at HEAD, never a backup, and never the device). Sent: nothing. Recorded: nothing. A syntax error is named with its line and the commit waits. Otherwise each device's golden is parsed into intent and rendered back through your edit, and compared line by line, as Approve… compares: what the render misses, what it invents, sections in another order, and lines the parser does not model that the device's committed intent has not acknowledged, each linking to where it is cleared. A device with no golden yet is named with **Capture…**, which records one from the device's page.
3. `commit`: one commit of the template, as you, with your reason as its subject. Read: the template at HEAD again, under the repository lock. Sent: nothing. Recorded: the commit (`template: <path> <your reason>`), and in the same commit the revocation of every approval whose template imports the file, each with why; the editor says which before you commit. The result names the commit and the revoked approvals, with **Approve…** for each: a deploy renders only through an approved template.
4. `moved`: if the template was committed by someone else after you opened it, nothing is written. Read: what you opened and what is committed now. Sent: nothing. Recorded: nothing. The card names both versions and who moved it, keeps your text to copy, and opens the template again on theirs.

## What editing does not do

- It contacts no device and changes no configuration: a deploy does that, through an approved template.
- It approves nothing: a committed edit revokes the approvals over it, and Approve… checks the committed template on every bound device before a deploy can use it.
- It reads no backup: every comparison is against a device's committed golden.
