# Minecraft Server Launcher - README

## Overview

This project provides a graphical user interface (GUI) for managing and running a Minecraft server. It is built using Python and PyQt5, offering an easy-to-use interface for server administrators. The application supports various server types (Vanilla, Forge, Mohist, Arclight, Fabric) and includes features such as server control, backup management, plugin downloading, and more.

## Features

- **Server Control**: Start, stop, and restart your Minecraft server with a single click.
- **Backup Management**: Create and restore server backups with ease.
- **Plugin Management**: Browse and download plugins for Bukkit/Spigot, Forge, Mohist, and Arclight.
- **Jar Downloader**: Download server JAR files for Vanilla, Forge, Mohist, Arclight, and Fabric.
- **File Explorer**: Browse and manage server files directly from the application.
- **Logs Viewer**: View server logs, including errors, warnings, and crash reports.
- **Customizable Settings**: Configure Java path, memory allocation, server directory, and more.

## Prerequisites

Before using this application, ensure you have the following installed on your system:

- **Python 3.6 or higher**: The application is written in Python.
- **PyQt5**: The GUI framework used by the application.
- **Java**: Required to run the Minecraft server. Ensure you have the correct version of Java installed for your server type.

You can install the required Python packages using pip:

```bash
pip install PyQt5 requests beautifulsoup4
```

## Usage

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/giogimic/minecraft-server-launcher.git
   cd minecraft-server-launcher
   ```

2. **Run the Application**:
   ```bash
   python run.py
   ```

3. **Configure Settings**:
   - Navigate to the **Settings** tab to configure the Java path, memory allocation, server directory, and backup directory.
   - Ensure the Java path points to the correct Java executable.

4. **Select Server JAR**:
   - Use the **Server Control** tab to select the server JAR file you want to run.

5. **Start the Server**:
   - Click the **Start Server** button in the **Server Control** tab to start the Minecraft server.

6. **Manage Backups**:
   - Use the **Administration** tab to create and restore server backups.

7. **Download Plugins**:
   - Use the **Plugin Directory** tab to browse and download plugins for your server.

8. **View Logs**:
   - Use the **Logs** tab to view server logs, including errors, warnings, and crash reports.

## Tabs Overview

- **Server Control**: Start, stop, and restart the server. Send commands to the server console.
- **Administration**: Manage server backups and edit server properties.
- **Creative Tools**: Send creative commands to the server.
- **Plugin Directory**: Browse and download plugins for various server types.
- **Jar Downloader**: Download server JAR files for Vanilla, Forge, Mohist, Arclight, and Fabric.
- **Settings**: Configure Java path, memory allocation, server directory, and backup directory.
- **Java Manager**: Detect installed Java versions and download popular Java versions.
- **File Explorer**: Browse and manage server files.
- **Logs**: View server logs, including errors, warnings, and crash reports.

## Backup Management

- **Create Backup**: Creates a ZIP archive of the server world and configuration files.
- **Restore Backup**: Restores a previously created backup.

## Jar Downloader

- **Vanilla**: Download official Minecraft server JAR files.
- **Forge**: Download Forge server JAR files.
- **Mohist**: Download Mohist server JAR files.
- **Arclight**: Download Arclight server JAR files.
- **Fabric**: Download Fabric server JAR files.

## Logs Viewer

- **Latest Log**: View the latest server log.
- **Errors**: View error messages from the server log.
- **Warns**: View warning messages from the server log.
- **Info**: View informational messages from the server log.
- **Mods**: View mod-related messages from the server log.
- **Crash**: View crash reports from the server log.

## Contributing

Contributions are welcome! If you have any suggestions, bug reports, or feature requests, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

## Acknowledgments

- **PyQt5**: For providing the GUI framework.
- **Mojang**: For the Minecraft server JAR files.
- **SpigotMC**: For the plugin repository.
- **CurseForge**: For the Forge mod repository.
- **MohistMC**: For the Mohist server JAR files.
- **Arclight**: For the Arclight server JAR files.
- **Fabric**: For the Fabric server JAR files.

---

Enjoy managing your Minecraft server with ease using this application! If you have any questions or need assistance, feel free to reach out.
