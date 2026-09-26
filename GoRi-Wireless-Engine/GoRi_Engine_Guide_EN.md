# 🌀 GoRi Wireless Engine - User Guide

> **Created by:** GoRi (고리) (khd57788@gmail.com)
> **License:** Free for everyone — individuals, groups, and corporations.
"See license terms at bottom of document"
---

*IMPORTANT* GoRi Engine is currently Windows-only.

> I'm a rural Korean uncle with zero coding experience and no English skills at all. ;;
I started using ComfyUI for YouTube content creation, but the English UI, complex setup, and spiderweb-like wires were too much for me. ;;
So I decided to at least get rid of the wires and made this myself.
My partner is free Gemini and the OpenCode agent. (Deep thanks to my partner.)
I used the free Bic pickle, MiniMax M2.5 Free, and Nemotron 3 Super Free model engines provided by OpenCode.
GoRi Engine is in beta and only tested on my PC, so there may be bugs.
I kindly ask for your understanding.

PS. Just so you know, it was REALLY hard to make. ㅜ,.ㅜ;;
If you'd like to support my work with a coffee,
or if you want the GoRi project to continue, please consider donating. (No pressure...)

-Voluntary Support-
International: PayPal - (khd57788@gmail.com)

---

## What is GoRi?

GoRi is a **wireless signal system** for ComfyUI.  
Instead of connecting nodes with wires, you assign **channel names** to each **input** and **output**.  
Nodes with the same channel name automatically communicate with each other — no wires needed!

Think of it like walkie-talkies. If two people both tune to channel 1, they can talk even if they're far apart.

---

*IMPORTANT* GoRi Engine is currently Windows-only.

💡 **Installation Tip** We highly recommend installing via the **Install via Git URL** option in ComfyUI Manager. This ensures you can easily get future updates with a single click using the manager's 'Update' or 'Update All' features!

## 1. Getting Started
- Extract the zip and place the `ComfyUI-GoRi-Wireless` folder into `ComfyUI/custom_nodes`.
- GoRi Engine automatically loads into all your nodes when ComfyUI starts (some exceptions apply).
- If you install a new node via Manager and refresh, GoRi Engine automatically attaches to it. (If it doesn't, press F5 or Ctrl+F5 to refresh.)

### 1.1 Turning the Engine On
Click the **hamburger menu button (☰)** next to the "Graph" button. A small window appears.  
The first switch shows **"Engine Active"** or **"Engine Paused"**.

- **Green light + "Engine Active"** = Engine is running.
- **Red light + "Engine Paused"** = Engine is paused (no wireless signals flow).

Click the switch to toggle it on or off.

### 1.2 Index Badge Switch
The second switch shows **"Index Box Active"** / **"Index Box Hidden"**.

- **ON**: A small tag like **GR-001**, **GR-002** appears on the top-right of every node.
- **OFF**: The tags are hidden.

### 1.3 Picker Size Adjustment
At the bottom of the hamburger menu popup, there is a **"Picker Size"** slider.
- Adjust the size of the channel selection picker from **1.0x to 3.0x**.
- The setting is automatically saved in your browser.

---

## 2. How Does Wireless Communication Work?

### 2.1 Switch Dots (Circles)
Each node's input and output has a **small circle** next to it.

- **Filled circle** = **Active** (sending or receiving a wireless signal).
- **No circle** = **Inactive** (not sending/receiving wireless signals).

**How to use the circles:**

| Action | Result |
|---|---|
| **Left-click** the circle | Toggle wireless on/off |
| **Right-click** the **channel name text** | Change the channel name (input box appears) |
| **Right-click** the **channel picker dropdown** | Change the channel name (input box appears) |

> 💡 Right-clicking the circle (dot) itself does nothing.<br>To rename, right-click the **channel name text** or the **dropdown**.

### 2.2 Channel Names
An active circle has a **channel name** next to it (e.g., `CH_001`, `my-channel`, etc.).

The rule is simple:
> **If an output and an input have the same channel name, they're connected — no wires needed!**

### 2.3 Scopes (Channel Zones)
Channels live inside a **Scope**.  
A Scope is a group on the canvas whose name starts with `GORI` (e.g., `GORI:BASE`, `GORI:FX`).

- Nodes inside a `GORI` group can **only talk to other nodes in the same group**.
- Nodes **outside** any `GORI` group use the **GLOBAL** scope and only communicate with other GLOBAL nodes.

This means different groups can reuse the same channel names without interfering with each other!

### 2.4 Broadcast Mode

Left-click the channel name on a sender (output) to open the channel picker dropdown.
Click the **current channel (green) one more time** in the dropdown to start **broadcast mode**.
- Receivers (inputs) that can connect to the broadcasting channel are shown in **purple** for 15 seconds.
- After 15 seconds, the broadcast automatically ends and the purple color disappears.

**How receivers connect to a broadcast:**
- Open the picker on a receiver node (input) to see purple channels.
- Click a purple channel to **wirelessly connect** — the channel then **disappears from all pickers on that node.**
- Other nodes' pickers still show it in purple (the broadcast continues).
- The connected channel appears in green, and when you open the picker again, it shows at the top of the list in green.

> 💡 When a node has multiple input ports (e.g., Image1, Image2, Image3), connecting one port to a purple channel removes it from the other ports' pickers too. This prevents duplicate connections.

---

### 2.5 Dynamic Slot Node Support

Special nodes like `TextEncodeQwenImageEditPlus` create their slots (input/output ports) dynamically each time.
GoRi Engine **additionally stores channel information directly on the node** for these cases,
so channel names and connection states are preserved even when slots are recreated.

> 🎯 After connecting, close and reopen the picker — the channel still shows up in green!

---

## 3. All Keyboard Shortcuts

| Key | When | What it does |
|---|---|---|
| **Esc** | Always | Closes any GoRi popup. Also **deselects all nodes** (removes blue highlights). |
| **G** | Engine on | **Ghost Signal Cleanup.** If nodes are selected, resets their GoRi data. If nothing is selected, removes unpaired "ghost" wireless data. |
| **S** | Engine on | **Scan & Re-index.** Assigns new numbers to all nodes (`GR-001`, `GR-002`, …), top-to-bottom, left-to-right. Also renames active channels to `CH_001`, `CH_002`, … in the same order. |
| **Shift + S** | Engine on | **Super Assembler.** Converts all **wired connections** to **wireless** and removes the actual wires. (Does not touch GetNode, SetNode, or Everywhere nodes.) |
| **Ctrl + B** | Anytime | When you **bypass** a node, automatically turns off all inputs that were listening to that node's channel. |
| **Ctrl + M** | Anytime | Same as above, but for **mute**. |
| **Alt + Drag** | On canvas | **Multi-clone.** Select multiple nodes, hold Alt and drag one of them — all selected nodes are cloned and move together! |

---

## 4. Automatic Behaviors

### 4.1 Guard Loop

A hidden "guard" always running in the background. It does this:

- **Detects new nodes** When pasting, finds new GoRi nodes and fixes channel names to avoid conflicts with existing ones.
- **Blocks receivers on disabled nodes** When a node is disabled/paused, the inputs listening to its channel are automatically turned off. When re-enabled, the inputs are restored.

### 4.2 Copy / Paste Handling

When pasting nodes:

- **Single node paste:** All wireless data is cleared (channels are preserved), like starting fresh.
- **Multi-node paste:** All channel names inside the pasted block are renamed to new unique names so they don't conflict with the original nodes.

### 4.3 Clone Handling

When you clone a node (Ctrl+C / Ctrl+V), GoRi temporarily hides the clone's index badge and switch dots while it sorts out the channel names.

### 4.4 Smart Connection (Signal Engine)

When you queue a prompt, GoRi scans all active outputs and inputs:
1. Collects all **senders** (outputs with channel names).
2. If **two or more senders** use the same channel, **nobody receives it** (safety mechanism).
3. For each active input, finds a sender with matching scope + channel.
4. **Smart type matching:** Whenever possible, connects outputs with the **same data type** (IMAGE → IMAGE, MODEL → MODEL, etc.).

---

## 5. Saved Settings

Automatically saved in your browser (`localStorage`):

- Engine on/off state
- Index badge on/off state
- Picker size (1.0x ~ 3.0x)
- Popup window size and position

---

## 6. Settings (Advanced)

### 6.1 Excluded Nodes

These nodes have GoRi features **blocked**:

- `GetNode`, `SetNode`
- `Reroute`, `ReroutePrimitive`
- Any node with "Everywhere" in its name (Anything Everywhere, Seed Everywhere, etc.)
- Nodes without GoRi engine can't use wireless connections.

These nodes continue to use their original wired connections.

---

## 7. Visual Elements

### Index Badge
A small tag on the top-right of each node: `GR-001`. Shows the node's sequence number.

### Switch Dot
Every small circle. Filled = active, no circle = inactive.

### Channel Label
Channel name shown in italics next to each circle.

### Bezier Curves (Wireless Signal Lines)
- Hover over a node to see which other nodes it's wirelessly connected to.
- Click a node to show curves between all nodes using the same channel. The curves stay until you deselect, giving you a visual of the invisible wireless connections!

### Color Coding
Each data type has its own color:
- **MODEL** = Purple
- **CLIP** = Yellow
- **VAE** = Red
- **IMAGE** = Green
- **LATENT** = Orange
- **CONDITIONING** = Gold
- **MASK** = Blue
- **CONTROL_NET** = Cyan

---

## 8. Tips
- Use **Scopes** (`GORI:` groups) to separate different parts of your workflow.
- Press **S** after adding new nodes for a clean re-index.
- Press **Shift+S** once to convert all wires to wireless. After that, you won't need wires anymore!
- If something behaves strangely, press **G** to clean up ghost signals.

---

[License and Terms of Use]

/* * =============================================================
 * Project: GoRi Switch Engine v1.0
 * Developer: GoRi (고리)
 * Version: 1.0 (Build 2026.05.18)
 * * [License and Terms of Use]
 * 1. Free Use: Individuals, groups, and corporations may all use it for free.
 * 2. Redistribution Prohibited: Unauthorized copying or redistribution 
 *    of this engine to other platforms is strictly prohibited.
 * 3. No Plagiarism or Theft: Any attempt to steal the source code or 
 *    redistribute it under a different name is strictly prohibited.
 * 4. Attribution: When sharing workflows, including 
 *    "Powered by GoRi Engine" is recommended.
 * * [Legal Notice]
 * This software was developed by GoRi. Unauthorized copying, modification, 
 * and especially commercial packaging/sale may be subject to legal action 
 * under intellectual property law.
 * (Security: 'GoRi-2026.04.15 k' watermark hidden in source)
 * * Contact: khd57788@gmail.com
 * =============================================================
 */
