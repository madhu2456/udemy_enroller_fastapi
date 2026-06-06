import type { ExistingContact, ContactQuery } from 'expo-contacts';
import { Fields, SortTypes } from 'expo-contacts/src/Contacts';
import Alert from './alerts.web';
import * as Notifications from 'expo-contacts';
const { PermissionStatus } = Notifications;

export { PermissionStatus, Fields, SortTypes };

const fakeContacts: ExistingContact[] = [
  {
    id: '1',
    contactType: 'person',
    name: 'John Doe',
    firstName: 'John',
    lastName: 'Doe',
    phoneNumbers: [
      { number: '+1 (555) 123-4567', isPrimary: true, label: 'mobile' },
      { number: '+1 (555) 987-6543', isPrimary: false, label: 'home' },
    ],
    emails: [
      { email: 'john.doe@example.com', isPrimary: true, label: 'work' },
      { email: 'john.personal@gmail.com', isPrimary: false, label: 'personal' },
    ],
    addresses: [
      {
        street: '123 Main St',
        city: 'New York',
        region: 'NY',
        postalCode: '10001',
        country: 'USA',
        label: 'home',
      },
    ],
    birthday: { day: 15, month: 5, year: 1990 },
    note: 'Met at conference',
  },
  {
    id: '2',
    contactType: 'person',
    name: 'Jane Smith',
    firstName: 'Jane',
    lastName: 'Smith',
    phoneNumbers: [{ number: '+1 (555) 234-5678', isPrimary: true, label: 'mobile' }],
    emails: [{ email: 'jane.smith@company.com', isPrimary: true, label: 'work' }],
    addresses: [
      {
        street: '456 Oak Ave',
        city: 'Los Angeles',
        region: 'CA',
        postalCode: '90210',
        country: 'USA',
        label: 'home',
      },
    ],
    birthday: { day: 3, month: 12, year: 1985 },
    note: 'College friend',
  },
  {
    id: '3',
    contactType: 'person',
    name: 'Bob Johnson',
    firstName: 'Bob',
    lastName: 'Johnson',
    phoneNumbers: [{ number: '+1 (555) 345-6789', isPrimary: true, label: 'mobile' }],
    emails: [{ email: 'bob.johnson@email.com', isPrimary: true, label: 'personal' }],
    addresses: [],
    birthday: { day: 22, month: 8, year: 1992 },
    note: 'Neighbor',
  },
  {
    id: '4',
    contactType: 'person',
    name: 'Alice Williams',
    firstName: 'Alice',
    lastName: 'Williams',
    phoneNumbers: [
      { number: '+1 (555) 456-7890', isPrimary: true, label: 'mobile' },
      { number: '+1 (555) 111-2222', isPrimary: false, label: 'work' },
    ],
    emails: [{ email: 'alice.williams@startup.com', isPrimary: true, label: 'work' }],
    addresses: [
      {
        street: '789 Pine St',
        city: 'San Francisco',
        region: 'CA',
        postalCode: '94102',
        country: 'USA',
        label: 'work',
      },
    ],
    birthday: { day: 10, month: 3, year: 1988 },
    note: 'Business partner',
  },
  {
    id: '5',
    contactType: 'person',
    name: 'Charlie Brown',
    firstName: 'Charlie',
    lastName: 'Brown',
    phoneNumbers: [{ number: '+1 (555) 567-8901', isPrimary: true, label: 'mobile' }],
    emails: [{ email: 'charlie.brown@gmail.com', isPrimary: true, label: 'personal' }],
    addresses: [],
    birthday: { day: 18, month: 11, year: 1995 },
    note: 'Gym buddy',
  },
];

let permissionStatus = {
  status: PermissionStatus.UNDETERMINED,
  expires: 'never',
  granted: false,
  canAskAgain: true,
};

// since we polyfill fake contacts, we always return true
export const isAvailableAsync = async () => {
  return true;
};

export const requestPermissionsAsync = async () => {
  if (permissionStatus.status === PermissionStatus.GRANTED) {
    return permissionStatus;
  }

  return new Promise((resolve) => {
    Alert.alert(
      '"Expo Go" Would Like to Access Your Contacts',
      'Allow Expo projects to access your contacts',
      [
        {
          text: "Don't Allow",
          onPress: () => {
            permissionStatus = {
              status: PermissionStatus.DENIED,
              expires: 'never',
              granted: false,
              canAskAgain: true,
            };
            resolve(permissionStatus);
          },
          style: 'default',
        },
        {
          text: 'Continue',
          onPress: () => {
            permissionStatus = {
              status: PermissionStatus.GRANTED,
              expires: 'never',
              granted: true,
              canAskAgain: false,
            };
            resolve(permissionStatus);
          },
          style: 'default',
        },
      ]
    );
  });
};

export const getPermissionsAsync = async () => {
  return permissionStatus;
};

export const getContactsAsync = async (options: ContactQuery = {}) => {
  const { sort = SortTypes.FirstName, pageSize, pageOffset } = options;

  let contacts = [...fakeContacts];

  if (sort === SortTypes.FirstName) {
    contacts.sort((a, b) => (a.firstName || '').localeCompare(b.firstName || ''));
  } else if (sort === SortTypes.LastName) {
    contacts.sort((a, b) => (a.lastName || '').localeCompare(b.lastName || ''));
  }

  if (pageSize && pageOffset !== undefined) {
    const startIndex = pageOffset * pageSize;
    contacts = contacts.slice(startIndex, startIndex + pageSize);
  }

  return {
    data: contacts,
    hasNextPage: false,
    hasPreviousPage: false,
    total: fakeContacts.length,
  };
};

export const getContactByIdAsync = async (id: string, _options: ContactQuery = {}) => {
  const contact = fakeContacts.find((c) => c.id === id);
  if (!contact) {
    throw new Error(`Contact with id ${id} not found`);
  }

  return contact;
};

export const addContactAsync = async (contact: ExistingContact) => {
  const newContact: ExistingContact = {
    id: Date.now().toString(),
    contactType: contact.contactType || 'person',
    name: contact.name || '',
    firstName: contact.firstName || '',
    lastName: contact.lastName || '',
    phoneNumbers: contact.phoneNumbers || [],
    emails: contact.emails || [],
    addresses: contact.addresses || [],
    birthday: contact.birthday,
    note: contact.note || '',
    middleName: contact.middleName,
    maidenName: contact.maidenName,
    namePrefix: contact.namePrefix,
    nameSuffix: contact.nameSuffix,
    nickname: contact.nickname,
    phoneticFirstName: contact.phoneticFirstName,
    phoneticMiddleName: contact.phoneticMiddleName,
    phoneticLastName: contact.phoneticLastName,
    company: contact.company,
    jobTitle: contact.jobTitle,
    department: contact.department,
    imageAvailable: contact.imageAvailable,
    image: contact.image,
    rawImage: contact.rawImage,
    dates: contact.dates,
    relationships: contact.relationships,
    instantMessageAddresses: contact.instantMessageAddresses,
    urlAddresses: contact.urlAddresses,
    nonGregorianBirthday: contact.nonGregorianBirthday,
    socialProfiles: contact.socialProfiles,
    isFavorite: contact.isFavorite,
  };

  fakeContacts.push(newContact);
  Alert.alert('Success', 'Contact added successfully!');
  return newContact.id;
};

export const updateContactAsync = async (contact: ExistingContact) => {
  const index = fakeContacts.findIndex((c) => c.id === contact.id);
  if (index === -1) {
    throw new Error(`Contact with id ${contact.id} not found`);
  }

  fakeContacts[index] = { ...fakeContacts[index], ...contact };
  return contact.id;
};

export const removeContactAsync = async (contactId: string) => {
  const index = fakeContacts.findIndex((c) => c.id === contactId);
  if (index === -1) {
    throw new Error(`Contact with id ${contactId} not found`);
  }

  fakeContacts.splice(index, 1);
  setTimeout(() => {
    Alert.alert('Success', 'Contact deleted successfully!');
  }, 500);
  return contactId;
};

const _createNoOpAsync = async () => {
  Alert.alert('Not supported in the builder', 'Please use the Expo Go app to test this feature');
  return { type: 'custom', data: null };
};

export const presentContactPickerAsync = async () => {
  return _createNoOpAsync();
};
export const getGroupsAsync = async () => {
  return _createNoOpAsync();
};
export const createGroupAsync = async () => {
  return _createNoOpAsync();
};
export const removeGroupAsync = async () => {
  return _createNoOpAsync();
};
export const updateGroupNameAsync = async () => {
  return _createNoOpAsync();
};

export default {
  Fields,
  SortTypes,
  PermissionStatus,
  isAvailableAsync,
  requestPermissionsAsync,
  getPermissionsAsync,
  getContactsAsync,
  getContactByIdAsync,
  addContactAsync,
  updateContactAsync,
  removeContactAsync,
  presentContactPickerAsync,
  getGroupsAsync,
  createGroupAsync,
  removeGroupAsync,
  updateGroupNameAsync,
};
