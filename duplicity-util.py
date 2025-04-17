#!/usr/bin/env python3
# duplicity-util.py - A backup management utility for Duplicity
# 
# @author Matthieu Neveu <https://github.com/mattneveu>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# <https://www.gnu.org/licenses/>

import argparse
import sys
import yaml
import os
import re
from datetime import datetime, date
from colorama import init, Fore, Style
import subprocess

# Initialize colorama
init()

CONFIG_FILE = "/usr/local/etc/duplicity_backup_jobs.yaml"
ENV_FILE = "/usr/local/etc/duplicity_env.sh"

class BackupManager:
    def __init__(self, config_file=CONFIG_FILE, env_file=ENV_FILE, nice_level=19, ionice_class=2, ionice_level=7):
        self.config_file = config_file
        self.env_file = env_file
        self.nice_level = nice_level
        self.ionice_class = ionice_class
        self.ionice_level = ionice_level
        self.config = self._load_config()
        self.env = self._load_env()
    
    def _print_success(self, message):
        """Print success message in green"""
        print(f"{Style.BRIGHT}{Fore.GREEN}{message}{Style.RESET_ALL}")

    def _print_error(self, message):
        """Print error message in red"""
        print(f"{Fore.RED}{message}{Style.RESET_ALL}", file=sys.stderr)

    def _load_config(self):
        """Load jobs configuration from YAML file"""
        try:
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self._print_error(f"Error: Configuration file '{self.config_file}' not found")
            return {}
        except yaml.YAMLError as e:
            self._print_error(f"Error loading YAML file: {e}")
            return {}
        
    def _load_env(self):
        """Load environment variables from shell script"""
        try:
            # Read the environment file and extract variables
            cmd = f"source {self.env_file} && env"
            pipe = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True, executable='/bin/bash')
            output = pipe.communicate()[0].decode('utf-8')
            
            env = {}
            for line in output.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    env[key] = value

            return env
        except Exception as e:
            self._print_error(f"Error loading environment variables: {e}")
            return {}

    def _validate_time_format(self, time_str):
        """
        Validate time string according to Duplicity's time formats:
        
        1. ISO datetime format: "2002-01-25T07:00:00+02:00"
        2. Interval format: "<number>(s|m|h|D|W|M|Y)" (can be combined)
        3. Date format: YYYY/MM/DD, YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY
        """
        # Check ISO datetime format
        iso_datetime_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$'
        if re.match(iso_datetime_pattern, time_str):
            try:
                # Alternative to fromisoformat for Python < 3.7
                # First try dateutil if available
                try:
                    import dateutil.parser
                    dateutil.parser.isoparse(time_str)
                    return True
                except ImportError:
                    # Manual parsing fallback
                    date_part, time_part = time_str.split('T', 1)
                    time_part, offset_part = time_part.rsplit('+', 1) if '+' in time_part else time_part.rsplit('-', 1)
                    
                    # Parse date
                    year, month, day = map(int, date_part.split('-'))
                    
                    # Parse time
                    hour, minute, second = map(int, time_part.split(':'))
                    
                    # Basic validation
                    if not (1 <= month <= 12 and 1 <= day <= 31 and 
                            0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                        raise ValueError("Invalid date/time values")
                    
                    return True
            except Exception:
                return False

        # Check interval format
        interval_pattern = r'^(\d+[smhDWMY])+$'
        if re.match(interval_pattern, time_str):
            # Validate each interval component
            components = re.findall(r'\d+[smhDWMY]', time_str)
            for comp in components:
                if not re.match(r'\d+[smhDWMY]$', comp):
                    break
            else:
                return True

        # Check date formats
        date_patterns = [
            (r'^\d{4}/\d{1,2}/\d{1,2}$', '%Y/%m/%d'),     # YYYY/MM/DD
            (r'^\d{4}-\d{1,2}-\d{1,2}$', '%Y-%m-%d'),     # YYYY-MM-DD
            (r'^\d{1,2}/\d{1,2}/\d{4}$', '%m/%d/%Y'),     # MM/DD/YYYY
            (r'^\d{1,2}-\d{1,2}-\d{4}$', '%m-%d-%Y')      # MM-DD-YYYY
        ]

        for pattern, date_format in date_patterns:
            if re.match(pattern, time_str):
                try:
                    # Try to parse the date to validate it
                    datetime.strptime(time_str, date_format)
                    return True
                except ValueError:
                    continue

        raise ValueError(
            "Invalid time format. Accepted formats:\n"
            "1. ISO datetime: '2002-01-25T07:00:00+02:00'\n"
            "2. Interval: '<number>(s|m|h|D|W|M|Y)' (can be combined), e.g., '1h30m'\n"
            "   s: seconds, m: minutes, h: hours\n"
            "   D: days, W: weeks, M: months, Y: years\n"
            "3. Date formats:\n"
            "   - YYYY/MM/DD  (e.g., 2002/3/5)\n"
            "   - YYYY-MM-DD  (e.g., 2002-3-5)\n"
            "   - MM/DD/YYYY  (e.g., 3/5/2002)\n"
            "   - MM-DD-YYYY  (e.g., 03-05-2002)"
        )

    def _run_duplicity_command(self, command, job_name=None):
        """Run a duplicity command with the proper environment and options"""
        try:
            # Combine current environment with duplicity-specific environment
            env = os.environ.copy()
            env.update(self.env)

            # Get duplicity options from environment
            duplicity_options = env.get('DUPLICITY_OPTIONS', '')          

            # Insert options right after 'duplicity' command but before the rest
            if 'duplicity' in command:
                # Split command into parts
                cmd_parts = command.split(' ', 1)
                # Reconstruct command with options
                if job_name:
                    command = f"{cmd_parts[0]} {duplicity_options} --name={job_name} {cmd_parts[1]}"
                else:
                    command = f"{cmd_parts[0]} {duplicity_options} {cmd_parts[1]}"

            # Apply nice and ionice directly to the duplicity command itself
            # NOT as a prefix to the entire command string
            env['PYTHONIOENCODING'] = 'utf-8'  # Ensure proper encoding for output

            # Check if command is a string or list
            if isinstance(command, str):
                # Convert string command to list for subprocess
                cmd_list = command.split()
            else:
                # Command is already a list
                cmd_list = command

            self._print_success(f"Executing command: {command}")

            # Use os.nice to set process priority
            os.nice(self.nice_level)
            
            # Set ionice via a separate command before launching duplicity
            if self.ionice_class in [1, 2, 3]:
                ionice_cmd = ["ionice", "-c", str(self.ionice_class)]
                if self.ionice_class == 2:  # best-effort class requires a level
                    ionice_cmd.extend(["-n", str(self.ionice_level)])
                    
                # Apply ionice to the current process
                subprocess.call(ionice_cmd + ["--ignore", "-p", str(os.getpid())])

            # Run the command
            process = subprocess.Popen(
                cmd_list,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            # Stream output in real-time
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    self._print_success(output.strip())
            
            # Get the return code and error output if any
            rc = process.poll()
            error_output = process.stderr.read()
            
            if rc != 0:
                self._print_error(f"Command failed with error:\n{error_output}")
                return False
                
            return True

        except Exception as e:
            self._print_error(f"Error executing duplicity command: {e}")
            return False
      
    def _local_cache_cleanup(self, job_name):
        self._print_success(f"Starting local cache cleanup for job '{job_name}'")
        env = os.environ.copy()
        env.update(self.env)
        CACHE_DIR = env.get('DUPLICITY_ARCHIVE_DIR', '')
        job_cache_dir = f"{CACHE_DIR}/{job_name}"
        if not os.path.exists(job_cache_dir):
            self._print_success("No cache directory found. Nothing to clean.")
            return True
        cleanup_find_cmd = ["find", job_cache_dir, "-type", "f", "-delete", "-print"]
        if job_name in self.config['jobs']:
            job = self.config['jobs'][job_name]
            retention = job['retention']
            fullifolder = job.get('fullifolder', retention)
            cleanup_find_cmd = ["find", job_cache_dir, "-type", "f", "-mtime", f"+{fullifolder}", "-delete", "-print"]
        try:
            self._print_success(f"Executing command: {' '.join(cleanup_find_cmd)}")
            process = subprocess.Popen(
                cleanup_find_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    self._print_success(f"Deleted: {output.strip()}")

            rc = process.poll()
            error_output = process.stderr.read()

            if rc != 0:
                self._print_error(f"Cleanup failed with error:\n{error_output}")
                return False

            self._print_success("Cache cleanup completed successfully")
            return True
        except Exception as e:
            self._print_error(f"Error during cleanup: {e}")
            return False
    
    def _execute_script(self, script_config, env=None, timeout=1800):
        """
        Execute a user-provided script with environment variables
        
        Args:
            script_path: Path to the script to execute
            env: Dictionary of environment variables to pass to the script
            
        Returns:
            Tuple (success, output, error)
        """
        try:
             # Handle different script configuration formats
            if isinstance(script_config, str):
                # Simple string path
                script_path = script_config
                script_args = []
            elif isinstance(script_config, list) and len(script_config) > 0:
                # Array format [path, arg1, arg2, ...]
                script_path = script_config[0]
                script_args = script_config[1:]
            else:
                return False, "", f"Invalid script configuration: {script_config}"
            if not os.path.exists(script_path):
                return False, "", f"Script not found: {script_path}"
                
            if not os.access(script_path, os.X_OK):
                return False, "", f"Script is not executable: {script_path}"

            # Build command with arguments
            command = [script_path] + script_args
            # Prepare environment
            script_env = os.environ.copy()
            if env and isinstance(env, dict):
                script_env.update(env)

            # Execute script
            args_display = " ".join(script_args) if script_args else ""
            if args_display:
                self._print_success(f"Executing pre_script: {script_path} with args: {args_display}")
            else:
                self._print_success(f"Executing pre_script: {script_path}")    
            process = subprocess.Popen(
                command,
                env=script_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Capture output
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                return False, "", f"Script timed out after {timeout} seconds"
            
            # Check return code
            if process.returncode != 0:
                return False, stdout, stderr
                
            return True, stdout, stderr
            
        except Exception as e:
            return False, "", str(e)


    def list_jobs(self):
        """List all configured backup jobs"""
        if not self.config['jobs']:
            self._print_success("No jobs configured")
            return
        
        self._print_success("Configured jobs:")
        for job_name, job_info in self.config['jobs'].items():
            self._print_success(f"\nJob: {job_name}")
            for key, value in job_info.items():
                self._print_success(f"  {key}: {value}")


    def restore_job(self, job_name, restore_path=None, time_spec=None, path_to_restore=None, show_progress=False, force=False):
        """Restore a backup job"""
       
        source = self.config['destination'] + job_name
        if restore_path:
            destination = restore_path
        else:
            destination = self.config['jobs'][job_name]['source']

        if not os.path.exists(destination):
            self._print_error(f"Error: Restoration path '{destination}' does not exist")
            return

        # Build duplicity command
        cmd_parts = ["duplicity restore"]

        # Show progress if requested
        if show_progress:
            cmd_parts.append("--progress")
        if force:
            cmd_parts.append("--force")
        
        if time_spec:
            try:
                self._validate_time_format(time_spec)
                cmd_parts.append("--time")
                cmd_parts.append(time_spec)
            except ValueError as e:
                self._print_error(f"Error: {e}")
                return

        if path_to_restore:
            cmd_parts.append(f"--file-to-restore {path_to_restore}")

        cmd_parts.extend([
            f"{source}",
            f"{destination}"
        ])

        command = " ".join(cmd_parts)
        self._print_success(f"Executing: {command}")
        self._run_duplicity_command(command, job_name)
        self._local_cache_cleanup(job_name)

    def trigger_backup(self, job_name, show_progress=False):
        """Trigger a backup job"""
        if job_name not in self.config['jobs']:
            self._print_error(f"Error: Job '{job_name}' not found")
            return

        job = self.config['jobs'][job_name]
        source = job['source']
        retention = job['retention']
        destination = self.config['destination'] + job_name

        # Check if pre-script is defined
        pre_script = job.get('pre_script')
        if pre_script:
            # Check if failing pre-script should abort backup
            abort_on_pre_script_failure = job.get('abort_on_pre_script_failure', True)
            
            # Execute pre-script
            self._print_success(f"Running pre-script for job '{job_name}'")
            
            # Get timeout value (default: 5 minutes)
            timeout = job.get('pre_script_timeout', 1800)
            # Prepare variables to pass to the script
            script_env = {
                'BACKUP_JOB_NAME': job_name,
                'BACKUP_SOURCE': source,
                'BACKUP_DESTINATION': destination,
                'BACKUP_TYPE': job.get('type', 'incremental')
            }
            
            success, output, error = self._execute_script(pre_script, script_env, timeout)
            
            # Display script output
            if output:
                self._print_success(f"Pre-script output:\n{output}")
                
            # Handle script failure
            if not success:
                self._print_error(f"Pre-script failed with error:\n{error}")
                
                if abort_on_pre_script_failure:
                    self._print_error(f"Aborting backup for job '{job_name}' due to pre-script failure")
                    return False
                else:
                    self._print_success(f"Continuing with backup despite pre-script failure")
            else:
                self._print_success(f"Pre-script successfully executed for job '{job_name}'")

        # Build duplicity command
        if job.get('type', 'incremental') == 'full':
            cmd_parts = ["duplicity full"]
        else:
            fullifolder = job.get('fullifolder', retention)
            cmd_parts = [f"duplicity incr --full-if-older-than {fullifolder}D"]

        # Show progress if requested
        if show_progress:
            cmd_parts.append("--progress")

        # Add compression option (default: enabled)
        compress = job.get('compress', True)
        if not compress:
            cmd_parts.append("--no-compression")
        
        # Add encryption option (default: disabled)
        encrypt = job.get('encrypt', False)
        if not encrypt:
            cmd_parts.append("--no-encryption")

        excludes = job.get('exclude', [])
        includes = job.get('include', [])
        if includes and isinstance(includes, list):
            for pattern in includes:
                # Remove quotes around the pattern
                pattern = pattern.strip("'\"")
                cmd_parts.append(f"--include")
                cmd_parts.append(f"{pattern}")
        if excludes and isinstance(excludes, list):
            for pattern in excludes:
                # Remove quotes around the pattern
                pattern = pattern.strip("'\"")
                cmd_parts.append(f"--exclude")
                cmd_parts.append(f"{pattern}")
        
        cmd_parts.extend([
            f"{source}",
            f"{destination}"
        ])
        command = " ".join(cmd_parts)
        self._print_success(f"Starting backup for job '{job_name}'")
        self._run_duplicity_command(command, job_name)

    def trigger_cleanup(self, job_name):
        """Trigger a cleanup for a job"""
        if job_name not in self.config['jobs']:
            self._print_error(f"Error: Job '{job_name}' not found")
            return

        job = self.config['jobs'][job_name]
        destination = self.config['destination'] + job_name
        retention = job['retention']

        # Build duplicity command
        command = f"duplicity remove-older-than {retention}D {destination} --force"
        
        self._print_success(f"Starting cleanup for job '{job_name}'")
        self._run_duplicity_command(command, job_name)
        self._local_cache_cleanup(job_name)
        

    def get_job_status(self, job_name):
        """Get the status of a backup job"""

        target = self.config['destination'] + job_name
        self._print_success(f"Status for job '{job_name}':")
        command = f"duplicity collection-status {target}"
        
        self._run_duplicity_command(command, job_name)

    def list_job_content(self, job_name, target_date=None):
        """List the content of a backup job at specific date"""

        target = self.config['destination'] + job_name
        cmd_parts = ["duplicity list-current-files"]

        if target_date:
            try:
                self._validate_time_format(target_date)
            except ValueError as e:
                self._print_error(f"Error: {e}")
                return
            cmd_parts.append(f"-t {target_date}")
            self._print_success(f"Listing content of backup '{job_name}' from {target_date}")
        else:
            self._print_success(f"Listing content of latest backup for '{job_name}'")

        cmd_parts.append(f"{target}")
        command = " ".join(cmd_parts)
        self._run_duplicity_command(command, job_name)


def main():
    parser = argparse.ArgumentParser(description="Backup management utility")
    parser.add_argument('action', choices=['list', 'restore', 'backup', 'status', 'content', 'cleanup'],
                       help="Action to perform")
    parser.add_argument('--job', help="Job name")
    parser.add_argument('-a', '--all', action='store_true', 
                       help="Perform action on all configured jobs")
    parser.add_argument('--restore-path', 
                       help="Restoration path (destination for restored files). Default is source path.")
    parser.add_argument('--path-to-restore', 
                       help="Specific path within the backup to restore")
    parser.add_argument('-t', '--time', 
                       help="Target date/time ISO (2002-01-25T07:00:00+02:00)")
    parser.add_argument('--nice', type=int, default=19,
                       help="Nice level (CPU priority, -20 to 19, default: 19)")
    parser.add_argument('--ionice-class', type=int, choices=[1, 2, 3], default=2,
                       help="IO Nice class (1:realtime, 2:best-effort, 3:idle, default: 2)")
    parser.add_argument('--ionice-level', type=int, choices=range(8), default=7,
                       help="IO Nice level (0-7, default: 7, only for best-effort class)")
    parser.add_argument('--progress', action='store_true',
                       help="Show progress during duplicity operations")
    parser.add_argument('--force', action='store_true',
                       help="Passing force option to duplicity commands")

    args = parser.parse_args()
    # Validate nice and ionice values
    if not -20 <= args.nice <= 19:
        print("Error: Nice value must be between -20 and 19")
        sys.exit(1)

    if args.ionice_class == 2 and not 0 <= args.ionice_level <= 7:
        print("Error: IO Nice level must be between 0 and 7 for best-effort class")
        sys.exit(1)
    
    # if args.action == 'restore' and not args.restore_path:
    #     parser.error("--restore-path is required when using the restore action")

    backup_manager = BackupManager(
        nice_level=args.nice,
        ionice_class=args.ionice_class,
        ionice_level=args.ionice_level
    )

    if args.action == 'list':
        backup_manager.list_jobs()
    elif args.action in ['restore', 'backup', 'status', 'content', 'cleanup']:
        if not args.job and not args.all:
            print("Error: Either a jobname --job or --all must be specified")
            sys.exit(1)
        
        if args.job and args.all:
            print("Error: Cannot specify both --job and --all")
            sys.exit(1)
        
        if args.all:
            for job_name in backup_manager.jobs.keys():
                print(f"\nProcessing job: {job_name}")
                if args.action == 'backup':
                    backup_manager.trigger_backup(job_name)
                elif args.action == 'status':
                    backup_manager.get_job_status(job_name)
                elif args.action == 'cleanup':
                    backup_manager.trigger_cleanup(job_name)
        else:
            if args.action == 'restore':
                backup_manager.restore_job(
                    args.job,
                    args.restore_path,
                    args.time,
                    args.path_to_restore,
                    show_progress=args.progress,
                    force=args.force
                )
            elif args.action == 'backup':
                backup_manager.trigger_backup(args.job, show_progress=args.progress)
            elif args.action == 'status':
                backup_manager.get_job_status(args.job)
            elif args.action == 'content':
                backup_manager.list_job_content(args.job, args.time)
            elif args.action == 'cleanup':
                backup_manager.trigger_cleanup(args.job)

if __name__ == "__main__":
    main()
